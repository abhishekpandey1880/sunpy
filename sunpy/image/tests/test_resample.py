import os

import numpy as np
import pytest

import astropy.units as u

import sunpy.data.test
import sunpy.map
from sunpy.image.resample import reshape_image_to_4d_superpixel


@pytest.fixture
def aia171_test_map():
    testpath = sunpy.data.test.rootdir
    return sunpy.map.Map(os.path.join(testpath, 'aia_171_level1.fits'))


@pytest.fixture
def shape(aia171_test_map):
    return np.array(aia171_test_map.data.shape)


def resample_meta(aia171_test_map, dimensions, method, center, minusone):
    map_resampled = aia171_test_map.resample(dimensions)
    return tuple(map_resampled.data.shape)


def resample_method(aia171_test_map, method):
    assert resample_meta(aia171_test_map, (512, 512) * u.pix, method, False, False) == (512, 512)
    assert resample_meta(aia171_test_map, (2056, 2056) * u.pix,
                         method, False, False) == (2056, 2056)
    assert resample_meta(aia171_test_map, (512, 512) * u.pix, method, False, True) == (512, 512)
    assert resample_meta(aia171_test_map, (2056, 2056) * u.pix, method, False, True) == (2056, 2056)
    assert resample_meta(aia171_test_map, (512, 512) * u.pix, method, True, False) == (512, 512)
    assert resample_meta(aia171_test_map, (2056, 2056) * u.pix, method, True, False) == (2056, 2056)
    assert resample_meta(aia171_test_map, (512, 512) * u.pix, method, True, True) == (512, 512)
    assert resample_meta(aia171_test_map, (2056, 2056) * u.pix, method, True, True) == (2056, 2056)


def test_resample_neighbor(aia171_test_map):
    resample_method(aia171_test_map, 'neighbor')


def test_resample_nearest(aia171_test_map):
    resample_method(aia171_test_map, 'nearest')


def test_resample_linear(aia171_test_map):
    resample_method(aia171_test_map, 'linear')


def test_resample_spline(aia171_test_map):
    resample_method(aia171_test_map, 'spline')


def test_reshape(aia171_test_map, shape):

    def _n(a, b, c):
        return int(np.floor((a-b)/c))

    # Dimension divides the array shape exactly with no remainder
    im = reshape_image_to_4d_superpixel(aia171_test_map.data, (2, 2), (0, 0))
    assert im.shape == (shape[0]/2, 2, shape[1]/2, 2)
    # Dimension divides the array shape exactly with remainder
    im = reshape_image_to_4d_superpixel(aia171_test_map.data, (7, 5), (0, 0))
    assert im.shape == (np.int(shape[0]/7), 7, np.int(shape[1]/5), 5)
    # Dimension divides the array shape exactly with no remainder, and there is
    # an offset
    im = reshape_image_to_4d_superpixel(aia171_test_map.data, (2, 2), (1, 1))
    assert im.shape == (np.int(shape[0]/2) - 1, 2, np.int(shape[1]/2) - 1, 2)
    # Dimension divides the array shape exactly with remainder, and there is
    # an offset
    d = (9, 7)
    o = (1, 4)
    im = reshape_image_to_4d_superpixel(aia171_test_map.data, d, o)
    assert im.shape == (_n(shape[0], o[0], d[0]), d[0],
                        _n(shape[1], o[1], d[1]), d[1])
    im = reshape_image_to_4d_superpixel(aia171_test_map.data, d, o)
    assert im.shape == (_n(shape[0], o[0], d[0]), d[0],
                        _n(shape[1], o[1], d[1]), d[1])

    d = (9, 7)
    o = (5, 4)
    im = reshape_image_to_4d_superpixel(aia171_test_map.data, d, o)
    assert im.shape == (_n(shape[0], o[0], d[0]), d[0],
                        _n(shape[1], o[1], d[1]), d[1])

    d = (9, 7)
    o = (4, 4)
    im = reshape_image_to_4d_superpixel(aia171_test_map.data, d, o)
    assert im.shape == (_n(shape[0], o[0], d[0]), d[0],
                        _n(shape[1], o[1], d[1]), d[1])
