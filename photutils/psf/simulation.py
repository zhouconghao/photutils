# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""
This module provides simulation utilities for creating images from PSF
models.
"""

import numpy as np

from photutils.datasets import make_model_image, make_model_params
from photutils.psf.utils import _get_psf_model_params
from photutils.utils._parameters import as_pair

__all__ = ['make_psf_model_image']

__doctest_requires__ = {'make_psf_model_image': ['scipy']}


def make_psf_model_image(shape, psf_model, n_sources, *, model_shape=None,
                         min_separation=1, border_size=None, seed=0,
                         progress_bar=False, **kwargs):
    """
    Make an example image containing PSF model images.

    Source parameters are randomly generated using an optional ``seed``.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the output image.

    psf_model : 2D `astropy.modeling.Model`
        The PSF model. The model must have parameters named ``x_0``,
        ``y_0``, and ``flux``, corresponding to the center (x, y)
        position and flux, or it must have 'x_name', 'y_name', and
        'flux_name' attributes that map to the x, y, and flux parameters
        (i.e., a model output from `make_psf_model`). The model must be
        two-dimensional such that it accepts 2 inputs (e.g., x and y)
        and provides 1 output.

    n_sources : int
        The number of sources to generate. If ``min_separation`` is too
        large, the number of requested sources may not fit within the
        given ``shape`` and therefore the number of sources generated
        may be less than ``n_sources``.

    model_shape : `None` or 2-tuple of int, optional
        The shape around the center (x, y) position that will used to
        evaluate the ``psf_model``. If `None`, then the shape will be
        determined from the ``psf_model`` bounding box (an error will be
        raised if the model does not have a bounding box).

    min_separation : float, optional
        The minimum separation between the centers of two sources. Note
        that if the minimum separation is too large, the number of
        sources generated may be less than ``n_sources``.

    border_size : `None`, tuple of 2 int, or int, optional
        The (ny, nx) size of the exclusion border around the image edges
        where no sources will be generated that have centers within
        the border region. If a single integer is provided, it will be
        used for both dimensions. If `None`, then a border size equal
        to half the (y, x) size of the evaluated PSF model (taking any
        oversampling into account) will be used.

    seed : int, optional
        A seed to initialize the `numpy.random.BitGenerator`. If `None`,
        then fresh, unpredictable entropy will be pulled from the OS.

    progress_bar : bool, optional
        Whether to display a progress bar when creating the sources. The
        progress bar requires that the `tqdm <https://tqdm.github.io/>`_
        optional dependency be installed. Note that the progress
        bar does not currently work in the Jupyter console due to
        limitations in ``tqdm``.

    **kwargs
        Keyword arguments are accepted for additional model parameters.
        The values should be 2-tuples of the lower and upper bounds for
        the parameter range. The parameter values will be uniformly
        distributed between the lower and upper bounds, inclusively. If
        the parameter is not in the input ``psf_model`` parameter names,
        it will be ignored.

    Returns
    -------
    data : 2D `~numpy.ndarray`
        The simulated image.

    table : `~astropy.table.Table`
        A table containing the (x, y, flux) parameters of the generated
        sources. The column names will correspond to the names of the
        input ``psf_model`` (x, y, flux) parameter names. The table will
        also contain an ``'id'`` column with unique source IDs.

    Examples
    --------
    >>> from photutils.psf import CircularGaussianPRF, make_psf_model_image
    >>> shape = (150, 200)
    >>> psf_model= CircularGaussianPRF(fwhm=3.5)
    >>> n_sources = 10
    >>> data, params = make_psf_model_image(shape, psf_model, n_sources,
    ...                                     flux=(100, 250),
    ...                                     min_separation=10,
    ...                                     seed=0)
    >>> params['x_0'].info.format = '.4f'  # optional format
    >>> params['y_0'].info.format = '.4f'
    >>> params['flux'].info.format = '.4f'
    >>> print(params)  # doctest: +FLOAT_CMP
     id   x_0      y_0      flux
    --- -------- -------- --------
      1 125.4749  72.2784 147.9522
      2  57.1803  38.6027 128.1262
      3  14.6211 116.0558 200.8790
      4  10.0741 132.6001 129.2661
      5 158.2683  43.1937 186.6532
      6 176.7725  80.2951 190.3359
      7 142.6864 133.6184 244.3635
      8 108.1142  12.5095 110.8398
      9 180.9235 106.5528 174.9959
     10 158.7488  90.5548 211.6146

    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from photutils.psf import CircularGaussianPRF, make_psf_model_image
        shape = (150, 200)
        psf_model= CircularGaussianPRF(fwhm=3.5)
        n_sources = 10
        data, params = make_psf_model_image(shape, psf_model, n_sources,
                                            flux=(100, 250),
                                            min_separation=10,
                                            seed=0)
        plt.imshow(data, origin='lower')

    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from photutils.psf import CircularGaussianPRF, make_psf_model_image
        shape = (150, 200)
        psf_model= CircularGaussianPRF(fwhm=3.5)
        n_sources = 10
        data, params = make_psf_model_image(shape, psf_model, n_sources,
                                            flux=(100, 250),
                                            min_separation=10,
                                            seed=0, sigma=(1, 2))
        plt.imshow(data, origin='lower')
    """
    psf_params = _get_psf_model_params(psf_model)

    if model_shape is not None:
        model_shape = as_pair('model_shape', model_shape, lower_bound=(0, 1))
    else:
        try:
            bbox = psf_model.bounding_box.bounding_box()
            model_shape = (int(np.round(bbox[0][1] - bbox[0][0])),
                           int(np.round(bbox[1][1] - bbox[1][0])))

        except NotImplementedError as exc:
            raise ValueError('model_shape must be specified if the model '
                             'does not have a bounding_box attribute') from exc

    if border_size is None:
        border_size = (np.array(model_shape) - 1) // 2

    other_params = {}
    if kwargs:
        # include only kwargs that are not x, y, or flux
        for key, val in kwargs.items():
            if key not in psf_model.param_names or key in psf_params[0:2]:
                continue  # skip the x, y parameters
            other_params[key] = val

    x_name, y_name = psf_params[0:2]
    params = make_model_params(shape, n_sources, x_name=x_name, y_name=y_name,
                               min_separation=min_separation,
                               border_size=border_size, seed=seed,
                               **other_params)

    data = make_model_image(shape, psf_model, params, model_shape=model_shape,
                            x_name=x_name, y_name=y_name,
                            progress_bar=progress_bar)

    return data, params
