import numpy as np
from ..element_h1 import ElementH1


class ElementTriMini(ElementH1):
    nodal_dofs = 1
    interior_dofs = 1
    dim = 2
    maxdeg = 3
    dofnames = ['u']
    doflocs = np.array([[0., 0.],
                        [1., 0.],
                        [0., 1.],
                        [1./3., 1./3.]])

    def lbasis(self, X, i):
        x, y = X

        if i == 0:
            phi = 1. - x - y
            dphi = np.array([-1. + 0. * x, -1. + 0. * x])
        elif i == 1:
            phi = x
            dphi = np.array([1. + 0. * x, 0. * x])
        elif i == 2:
            phi = y
            dphi = np.array([0. * x, 1. + 0. * x])
        elif i == 3:
            phi = 27. * x * y * (1. - x - y)
            dphi = 27. * np.array([y * (1. - x - y) - x * y,
                                   x * (1. - x - y) - x * y])
        else:
            self._index_error()

        return phi, dphi