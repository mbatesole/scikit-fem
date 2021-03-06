from skfem import *
from skfem.models.poisson import laplace, unit_load

import numpy as np

from docs.examples.ex17 import mesh, basis, radii,\
    joule_heating, thermal_conductivity


insulation = np.unique(basis.element_dofs[:, mesh.subdomains['insulation']])
temperature = np.zeros(basis.N)
wire = basis.complement_dofs(insulation)
wire_basis = InteriorBasis(mesh, basis.elem, elements=mesh.subdomains['wire'])
L = asm(laplace, wire_basis)
f = asm(unit_load, wire_basis)
temperature = solve(*condense(thermal_conductivity['wire'] * L,
                              joule_heating * f,
                              D=insulation))

if __name__ == '__main__':
    from os.path import splitext
    from sys import argv
    from skfem.visuals.matplotlib import draw, plot

    T0 = {'skfem': basis.interpolator(temperature)(np.zeros((2, 1)))[0],
          'exact':
          joule_heating * radii[0]**2 / 4 / thermal_conductivity['wire']}
    print('Central temperature:', T0)

    ax = draw(mesh)
    plot(mesh, temperature[basis.nodal_dofs.flatten()],
         ax=ax, edgecolors='none', colorbar=True)
    ax.get_figure().savefig(splitext(argv[0])[0] + '_solution.png')
