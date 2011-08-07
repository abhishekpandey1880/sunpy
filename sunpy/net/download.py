# -*- coding: utf-8 -*-
# Author: Florian Mayer <florian.mayer@bitsrc.org>

import os
import urllib2
import select
import socket
import threading
import itertools

from collections import defaultdict, deque

class IDPool(object):
    """
    Pool that returns unique identifiers in a thread-safe way.
    
    Identifierers obtained using the get method are guaranteed to not be
    returned by it again until they are released using the release method.
    
        >>> pool = IDPool()
        >>> pool.get()
        0
        >>> pool.get()
        1
        >>> pool.get()
        2
        >>> pool.release(1)
        >>> pool.get()
        1
        >>> 
    """
    def __init__(self):
        self.max_id = -1
        self.free_ids = []
        
        self._lock = threading.Lock()
    
    def get(self):
        """ Return a new integer that is unique in this pool until
        it is released. """
        self._lock.acquire()
        try:
            if self.free_ids:
                return self.free_ids.pop()
            else:
                self.max_id += 1
                return self.max_id
        finally:
            self._lock.release()
    
    def release(self, id_):
        """ Release the id. It can now be returned by get again.
        
        Will reset the IDPool if the last id in use is released. """
        self._lock.acquire()
        try:
            self.free_ids.append(id_)
            if len(self.free_ids) == self.max_id + 1:
                self.reset()
        finally:
            self._lock.release()
    
    def reset(self):
        """ Reset the state of the IDPool. This should only be called when
        no identifier is in use. """
        self.max_id = -1
        self.free_ids = []


def socketpair():
    """ Return pair of connected sockets. Unlike socket.socketpair this
    is platform independant. However, if socket.socketpair is available,
    it is used here as well. """
    if hasattr(socket, 'socketpair'):
        # Unix.
        return socket.socketpair()
    
    try:
        acceptor = socket.socket()
        # Random port. Only accept local connections.
        acceptor.bind(('127.0.0.1', 0))
        # We know we'll only get one connection.
        acceptor.listen(1)

        one = socket.socket()
        one.connect(acceptor.getsockname())
        
        other = acceptor.accept()[0]
    finally:
        acceptor.close()
    return one, other


class Reactor(object):
    def __init__(self):
        self.syncr, self.synce = socketpair()
        self.ids = IDPool()
        self.call = []
        self.tcalls = {}
        self.callb = {}
        self.running = False
    
    def _unset_running(self):
        self.running = False
    
    def stop(self):
        self.call_sync(self._unset_running)
    
    def run(self):
        self.running = True
        while self.running:
            ret = self.poll()
            self._call_calls()
            self._call_tcalls()
            for fd in ret:
                try:
                    fun, args, kwargs = self.callb[fd]
                except KeyError:
                    continue
                fun(*args, **kwargs)
    
    def poll(self):
        raise NotImplementedError
    
    def call_sync(self, fun, args=None, kwargs=None):
        self.call.append(
            (fun,
             [] if args is None else args,
             {} if kwargs is None else kwargs
             )
        )
        self.synce.send('m')
    
    def _call_tcalls(self):
        for call in list(self.tcalls.itervalues()):
            fun, args, kwargs = call
            fun(*args, **kwargs)
    
    def add_tcall(self, fun, args=None, kwargs=None):
        id_ = self.ids.get()
        self.tcalls[id_] = (
            fun, [] if args is None else args, {} if kwargs is None else kwargs
        )
        return id_
    
    def rem_tcall(self, id_):
        del self.tcalls[id_]
        self.ids.release(id_)
    
    def _call_calls(self):
        for call in self.call:
            fun, args, kwargs = call
            fun(*args, **kwargs)
            self.syncr.recv(1)
        self.call = []
    
    def add_fd(self, fd, callback, args=None, kwargs=None):
        self.callb[fd] = (
            callback,
            [] if args is None else args,
            {} if kwargs is None else kwargs
        )
    
    def rem_fd(self, fd):
        del self.callb[fd]


class SelectReactor(Reactor):
    avail = hasattr(select, 'select')
    def __init__(self, fds=None):
        Reactor.__init__(self)
        self.fds = set() if fds is None else fds
        self.fds.add(self.syncr)
    
    def poll(self):
        return select.select(self.fds, [], [])[0]
    
    def add_fd(self, fd, callback, args=None, kwargs=None):
        super(SelectReactor, self).add_fd(fd, callback, args, kwargs)
        self.fds.add(fd)
        
    def rem_fd(self, fd):
        super(SelectReactor, self).rem_fd(fd)
        self.fds.remove(fd)
    
    def close(self):
        pass


# FIXME: Add [E]PollReactor and KQueueReactor.
DReactor = None
for reactor in [SelectReactor]:
    if reactor.avail:
        DReactor = reactor

if DReactor is None:
    raise EnvironmentError


def default_name(path, sock, url):
    name = sock.headers.get('Content-Disposition', url.rsplit('/', 1)[-1])
    return os.path.join(path, name)


class Downloader(object):
    def __init__(self, max_conn=5, max_total=20):
        self.max_conn = max_conn
        self.max_total = max_total
        self.conns = 0
        
        self.connections = defaultdict(int) # int() -> 0
        self.q = defaultdict(deque)
        
        self.reactor = DReactor()
        self.buf = 9096
    
    def _download(self, sock, fd, callback, id_=None):
        rec = sock.read(self.buf)
        if not rec:
            fun, args, kwargs = callback
            fun(*args, **kwargs)
            
            if id_ is not None:
                self.reactor.rem_tcall(id_)
            else:
                self.reactor.rem_fd(sock)
            fd.close()
        else:
            fd.write(rec)
    
    def _start_download(self, url, path, callback):
        server = url.split('/')[0]
        
        self.connections[server] += 1
        self.conns += 1
        
        sock = urllib2.urlopen(url)
        fullname = path(sock, url)
        
        try:
            sock.fileno()
        except AttributeError:
            nofileno = True
        else:
            nofileno = False
            
        args = [
                sock, open(fullname, 'w'),
                (self._close, [callback, [{'path': fullname}], server], {}),
        ]
        if nofileno:
            id_ = self.reactor.add_tcall(self._download, args)
            args.append(id_)
        else:
            self.reactor.add_fd(sock, self._download, args)
    
    def _attempt_download(self, url, path, callback):
        server = url.split('/')[0]
        
        if self.connections[server] < self.max_conn and self.conns < self.max_total:
            self._start_download(url, path, callback)
            return True
        return False

    def download(self, url, path, callback=None):
        server = url.split('/')[0]
        
        if not self._attempt_download(url, path, callback):
            self.q[server].append((url, path, callback))
    
    def _close(self, callback, args, server):
        callback(*args)
        
        if self.q[server]:
            self._start_download(*self.q[server].pop())
        else:
            self.connections[server] -= 1
            self.conns -= 1
            
            for k, v in self.q.iteritems():
                while v:
                    if self._attempt_download(*v[0]):
                        v.pop()
                        if self.conns == self.max_total:
                            return
                    else:
                        break


if __name__ == '__main__':
    import tempfile
    from functools import partial
    
    def wait_for(n):
        c = iter(xrange(n - 1))
        def _fun(handler):
            print 'Hello', repr(handler)
            if next(c, None) is None:
                print 'Bye'
                dw.reactor.stop()
        return _fun
    
    
    callb = wait_for(4)
    
    path_fun = partial(default_name, tempfile.mkdtemp())
    
    dw = Downloader(1, 2)
    dw.download('ftp://speedtest.inode.at/speedtest-5mb', path_fun, callb)
    dw.download('ftp://speedtest.inode.at/speedtest-20mb', path_fun, callb)
    dw.download('https://bitsrc.org', path_fun, callb)
    dw.download('ftp://speedtest.inode.at/speedtest-100mb', path_fun, callb)
    
    print dw.conns
    
    dw.reactor.run()
