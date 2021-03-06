import warnings
from typing import List, Optional, NamedTuple,\
    Any, Tuple, Dict, TypeVar

import numpy as np
from numpy import ndarray

from skfem.assembly.dofs import Dofs
from skfem.element.discrete_field import DiscreteField
from skfem.element.element_composite import ElementComposite
from skfem.element.element_vector_h1 import ElementVectorH1


BasisType = TypeVar('BasisType', bound='Basis')


class Basis:
    """The finite element basis is evaluated at global quadrature points
    and cached inside this object.

    Please see the following implementations:

    - :class:`~skfem.assembly.InteriorBasis`, basis functions inside elements
    - :class:`~skfem.assembly.FacetBasis`, basis functions on element boundaries

    """

    N: int = 0
    dofnames: List[str] = []

    def __init__(self, mesh, elem, mapping, intorder):
        if mapping is None:
            self.mapping = mesh.mapping()
        else:
            self.mapping = mapping

        self._build_dofnum(mesh, elem)

        if not isinstance(mesh, elem.mesh_type):
            raise ValueError("Incompatible Mesh and Element.")

        # human readable names
        self.dofnames = elem.dofnames

        # global degree-of-freedom location
        # disabled for MappingMortar by checking mapping.maps
        if hasattr(elem, 'doflocs') and not hasattr(mapping, 'maps'):
            doflocs = self.mapping.F(elem.doflocs.T)
            self.doflocs = np.zeros((doflocs.shape[0], self.N))

            # match mapped dofs and global dof numbering
            for itr in range(doflocs.shape[0]):
                for jtr in range(self.element_dofs.shape[0]):
                    self.doflocs[itr, self.element_dofs[jtr]] =\
                        doflocs[itr, :, jtr]

        self.mesh = mesh
        self.elem = elem

        self.Nbfun = self.element_dofs.shape[0]

        if intorder is None:
            self.intorder = 2 * self.elem.maxdeg
        else:
            self.intorder = intorder

        self.nelems = None # subclasses should overwrite

        self.refdom = mesh.refdom
        self.brefdom = mesh.brefdom

    def _build_dofnum(self, mesh, element):
        """Build global degree-of-freedom numbering."""
        # vertex dofs
        self.nodal_dofs = np.reshape(
            np.arange(element.nodal_dofs * mesh.p.shape[1], dtype=np.int64),
            (element.nodal_dofs, mesh.p.shape[1]),
            order='F')
        offset = element.nodal_dofs * mesh.p.shape[1]

        # edge dofs
        if mesh.dim() == 3: 
            self.edge_dofs = np.reshape(
                np.arange(element.edge_dofs * mesh.edges.shape[1],
                          dtype=np.int64),
                (element.edge_dofs, mesh.edges.shape[1]),
                order='F') + offset
            offset = offset + element.edge_dofs * mesh.edges.shape[1]
        else:
            self.edge_dofs = np.empty((0,0))

        # facet dofs
        self.facet_dofs = np.reshape(
            np.arange(element.facet_dofs * mesh.facets.shape[1],
                      dtype=np.int64),
            (element.facet_dofs, mesh.facets.shape[1]),
            order='F') + offset
        offset = offset + element.facet_dofs * mesh.facets.shape[1]

        # interior dofs
        self.interior_dofs = np.reshape(
            np.arange(element.interior_dofs * mesh.t.shape[1], dtype=np.int64),
            (element.interior_dofs, mesh.t.shape[1]),
            order='F') + offset

        # global numbering
        self.element_dofs = np.zeros((0, mesh.t.shape[1]), dtype=np.int64)

        # nodal dofs
        for itr in range(mesh.t.shape[0]):
            self.element_dofs = np.vstack((
                self.element_dofs,
                self.nodal_dofs[:, mesh.t[itr]]
            ))

        # edge dofs
        if mesh.dim() == 3:
            for itr in range(mesh.t2e.shape[0]):
                self.element_dofs = np.vstack((
                    self.element_dofs,
                    self.edge_dofs[:, mesh.t2e[itr]]
                ))

        # facet dofs
        if mesh.dim() >= 2:
            for itr in range(mesh.t2f.shape[0]):
                self.element_dofs = np.vstack((
                    self.element_dofs,
                    self.facet_dofs[:, mesh.t2f[itr]]
                ))

        # interior dofs
        self.element_dofs = np.vstack((self.element_dofs, self.interior_dofs))

        # total dofs
        self.N = np.max(self.element_dofs) + 1

    def complement_dofs(self, *D):
        if type(D[0]) is dict:
            # if a dict of Dofs objects are given, flatten all
            D = tuple(D[0][key].all() for key in D[0])
        return np.setdiff1d(np.arange(self.N), np.concatenate(D))

    def _get_dofs(self,
                  facets: ndarray,
                  skip: List[str] = []):
        """Return :class:`skfem.assembly.Dofs` corresponding to facets."""
        m = self.mesh
        nodal_ix = np.unique(m.facets[:, facets].flatten())
        facet_ix = facets

        if m.dim() == 3:
            edge_candidates = m.t2e[:, m.f2t[0, facets]].flatten()
            # subset of edges that share all points with the given facets
            subset_ix = np.nonzero(
                np.prod(np.isin(m.edges[:, edge_candidates],
                                m.facets[:, facets].flatten()),
                        axis=0)
            )[0]
            edge_ix = np.intersect1d(
                m.boundary_edges(),
                edge_candidates[subset_ix]
            )
        else:
            edge_ix = []

        n_nodal = self.nodal_dofs.shape[0]
        n_facet = self.facet_dofs.shape[0]
        n_edge = self.edge_dofs.shape[0]

        # group dofs based on 'dofnames' on different topological entities
        nodals = {
            self.dofnames[i]: np.zeros((0, len(nodal_ix)), dtype=np.int64)
            for i in range(n_nodal) if self.dofnames[i] not in skip
        }
        for i in range(n_nodal):
            if self.dofnames[i] not in skip:
                nodals[self.dofnames[i]] =\
                    np.vstack((nodals[self.dofnames[i]],
                               self.nodal_dofs[i, nodal_ix]))
        off = n_nodal

        facets = {
            self.dofnames[i + off]: np.zeros((0, len(facet_ix)), dtype=np.int64)
            for i in range(n_facet) if self.dofnames[i + off] not in skip
        }
        for i in range(n_facet):
            if self.dofnames[i + off] not in skip:
                facets[self.dofnames[i + off]] =\
                    np.vstack((facets[self.dofnames[i + off]],
                               self.facet_dofs[i, facet_ix]))
        off += n_facet

        edges = {
            self.dofnames[i + off]: np.zeros((0, len(edge_ix)), dtype=np.int64)
            for i in range(n_edge) if self.dofnames[i + off] not in skip
        }
        for i in range(n_edge):
            if self.dofnames[i + off] not in skip:
                edges[self.dofnames[i + off]] =\
                    np.vstack((edges[self.dofnames[i + off]],
                               self.edge_dofs[i, edge_ix]))

        return Dofs(
            nodal={k: nodals[k].flatten() for k in nodals},
            facet={k: facets[k].flatten() for k in facets},
            edge={k: edges[k].flatten() for k in edges}
        )

    def find_dofs(self,
                  facets: Dict[str, ndarray] = None,
                  skip: List[str] = []) -> Dict[str, Dofs]:
        """Return global DOF numbers corresponding to facets.

        Parameters
        ----------
        facets
            A dictionary of facet indices. If None, use self.mesh.boundaries
            if set or otherwise use {'all': self.mesh.boundary_facets()}.
        skip
            List of dofnames to skip.

        Returns
        -------
        Dict[str, Dofs]
            A dictionary of :class:`skfem.assembly.dofs.Dofs` objects.

        """
        if facets is None:
            if self.mesh.boundaries is None:
                facets = {'all': self.mesh.boundary_facets()}
            else:
                facets = self.mesh.boundaries

        return {k: self._get_dofs(facets[k], skip=skip) for k in facets}

    def get_dofs(self, facets: Optional[Any] = None):
        """Return global DOF numbers corresponding to facets (e.g. boundaries).

        Parameters
        ----------
        facets
            A list of facet indices. If None, find facets by
            Mesh.boundary_facets().  If callable, call Mesh.facets_satisfying to
            get facets. If array, find the corresponding dofs. If dict of
            arrays, find dofs for each entry. If dict of callables, call
            Mesh.facets_satisfying for each entry to get facets and then find
            dofs for those.

        Returns
        -------
        Dofs
            A subset of degrees-of-freedom as :class:`skfem.assembly.dofs.Dofs`.

        """
        warnings.warn(("Basis.get_dofs is removed in the next major"
                       " release. Use Basis.find_dofs instead."),
                      DeprecationWarning)

        if facets is None:
            facets = self.mesh.boundary_facets()
        elif callable(facets):
            facets = self.mesh.facets_satisfying(facets)
        if isinstance(facets, dict):
            def to_indices(f):
                if callable(f):
                    return self.mesh.facets_satisfying(f)
                return f
            return {k: self._get_dofs(to_indices(facets[k])) for k in facets}
        else:
            return self._get_dofs(facets)

    def default_parameters(self):
        """This is used by :func:`skfem.assembly.asm` to get the default
        parameters for 'w'."""
        raise NotImplementedError("Default parameters not implemented.")

    def interpolate(self, w: ndarray) -> Dict[str, DiscreteField]:
        """Interpolate a solution vector to quadrature points.

        Parameters
        ----------
        w
            A solution vector.

        Returns
        -------
        DiscreteField or (DiscreteField, ...)
            The solution vector interpolated at quadrature points.
            If Basis consist of a single component, returns only
            one DiscreteField. If Basis consists of multiple components,
            returns a tuple.

        """
        if w.shape[0] != self.N:
            raise ValueError("Input array has wrong size.")

        refs = self.basis[0]
        dfs: List[DiscreteField] = []

        # loop over solution components
        for c in range(len(refs)):
            ref = refs[c]
            fs = []

            def linear_combination(n, refn):
                """Global discrete function at quadrature points."""
                out = 0. * refn.copy()
                for i in range(self.Nbfun):
                    values = w[self.element_dofs[i]][:, None]
                    if len(refn.shape) == 2:  # values
                        out += values * self.basis[i][c][n]
                    elif len(refn.shape) == 3:  # derivatives
                        for j in range(out.shape[0]):
                            out[j, :, :] += values * self.basis[i][c][n][j]
                    elif len(refn.shape) == 4:  # second derivatives
                        for j in range(out.shape[0]):
                            for k in range(out.shape[1]):
                                out[j, k, :, :] += \
                                    values * self.basis[i][c][n][j, k]
                    elif len(refn.shape) == 5:  # third derivatives
                        #import pdb; pdb.set_trace()
                        for j in range(out.shape[0]):
                            for k in range(out.shape[1]):
                                for l in range(out.shape[2]):
                                    out[j, k, l, :, :] += \
                                        values * self.basis[i][c][-1][n][j, k, l]
                    elif len(refn.shape) == 6:  # fourth derivatives
                        for j in range(out.shape[0]):
                            for k in range(out.shape[1]):
                                for l in range(out.shape[2]):
                                    for m in range(out.shape[3]):
                                        out[j, k, l, m, :, :] += \
                                            values *\
                                            self.basis[i][c][-1][n][j, k, l, m]
                    else:
                        raise ValueError("The requested order of "
                                         "derivatives not supported.")
                return out

            # interpolate first and second derivatives
            for n in range(len(ref) - 1):
                if ref[n] is not None:
                    fs.append(linear_combination(n, ref[n]))
                else:
                    fs.append(None)

            # interpolate high-order derivatives
            fs.append([])

            if ref[-1] is not None:
                for n in range(len(ref[-1])):
                    fs[-1].append(linear_combination(n, ref[-1][n]))

            dfs.append(DiscreteField(*fs))

        if len(dfs) > 1:
            return tuple(dfs)
        return dfs[0]

    def split_indices(self) -> List[ndarray]:
        """Return indices for the solution components."""
        if isinstance(self.elem, ElementComposite):
            off = np.zeros(4, dtype=np.int)
            output = [None] * len(self.elem.elems)
            for k in range(len(self.elem.elems)):
                e = self.elem.elems[k]
                output[k] = np.concatenate((
                    self.nodal_dofs[off[0]:(off[0] + e.nodal_dofs)].flatten(),
                    self.edge_dofs[off[1]:(off[1] + e.edge_dofs)].flatten(),
                    self.facet_dofs[off[2]:(off[2] + e.facet_dofs)].flatten(),
                    self.interior_dofs[off[3]:(off[3] + e.interior_dofs)].flatten()
                )).astype(np.int)
                off += np.array([e.nodal_dofs,
                                 e.edge_dofs,
                                 e.facet_dofs,
                                 e.interior_dofs])
            return output
        raise ValueError("Basis.elem has only a single component!")

    def split_bases(self) -> List[BasisType]:
        """Return Basis objects for the solution components."""
        if isinstance(self.elem, ElementComposite):
            return [type(self)(self.mesh, e, self.mapping, self.intorder)
                    for e in self.elem.elems]
        raise ValueError("Basis.elem has only a single component!")

    def split(self, x: ndarray) -> List[Tuple[ndarray, BasisType]]:
        """Split solution vector into components."""
        xs = [x[ix] for ix in self.split_indices()]
        return list(zip(xs, self.split_bases()))

    def zero_w(self) -> ndarray:
        """Return a zero array with correct dimensions for
        :func:`~skfem.assembly.asm`."""
        return np.zeros((self.nelems, len(self.W)))

    def zeros(self) -> ndarray:
        """Return a zero array with same dimensions as the solution."""
        return np.zeros(self.N)
