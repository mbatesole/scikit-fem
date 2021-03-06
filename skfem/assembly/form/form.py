from typing import Any, Callable, Optional, Tuple, Union

import numpy as np
from numpy import ndarray
from scipy.sparse import coo_matrix

from .form_parameters import FormParameters
from ..basis import Basis
from ...element import DiscreteField


class FormDict(dict):

    def __getattr__(self, attr):
        return self[attr].value


class Form:

    def __init__(self, form: Callable):
        self.form = form

    def __call__(self, *args):
        return self.assemble(self.kernel(*args))

    def _kernel(self):
        raise NotImplementedError

    def assemble(self):
        raise NotImplementedError

    @staticmethod
    def dictify(w):
        """Support some legacy input formats for 'w'."""
        for k in w:
            if isinstance(w[k], DiscreteField):
                continue
            elif isinstance(w[k], ndarray):
                w[k] = DiscreteField(w[k])
            elif isinstance(w[k], list):
                w[k] = DiscreteField(np.array([z.f for z in w[k]]),
                                     np.array([z.df for z in w[k]]))
            elif isinstance(w[k], tuple):
                w[k] = DiscreteField(*w[k])
            else:
                raise ValueError("The given type '{}' for the list of extra "
                                 "form parameters w cannot be converted to "
                                 "DiscreteField.".format(type(w)))
        return w

    @staticmethod
    def _assemble_scipy_matrix(data, rows, cols, shape=None):
        K = coo_matrix((data, (rows, cols)), shape=shape)
        K.eliminate_zeros()
        return K.tocsr()

    @staticmethod
    def _assemble_numpy_vector(data, rows, cols, shape=None):
        return coo_matrix((data, (rows, cols)),
                          shape=shape).toarray().T[0]
