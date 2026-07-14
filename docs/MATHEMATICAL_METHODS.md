# Mathematical methods and algorithmic definitions

This document specifies the quantities computed by **UrbanFractal Topology 0.4.1**. It distinguishes mathematical definitions from finite-resolution estimators and records the conditions under which inter-city comparison is meaningful.

## 1. Analysis domain and rasterization

Let \(\Omega\subset\mathbb{R}^2\) be the supplied city boundary and let
\(B=\bigcup_k B_k\subset\Omega\) be the union of cleaned building-footprint polygons. Both are projected to a metric CRS and rasterized on the same square grid with pixel side \(a\) metres.

The binary arrays are

\[
M_{ij}=\mathbf 1\{\text{cell centre lies in }B\},\qquad
\Omega_{ij}=\mathbf 1\{\text{cell centre lies in }\Omega\}.
\]

All planar calculations use \(M\leftarrow M\cap\Omega\). Pixels in the bounding rectangle but outside \(\Omega\) are excluded rather than treated as urban voids. The default cell-centre rule avoids the systematic area inflation produced by `all_touched=True` at coarse resolution.

Raster fidelity is checked by

\[
\varepsilon_A=
\frac{|A_{\mathrm{raster}}-A_{\mathrm{vector}}|}{A_{\mathrm{vector}}}.
\]

## 2. Box-counting dimension of the building footprint

For box side \(\epsilon\), let \(N(\epsilon)\) be the number of boxes intersecting the rasterized building set. Four grid origins are tested: zero and half-box shifts in both coordinate directions. The conservative minimum count is used for the primary fit, while the mean and coefficient of variation quantify origin sensitivity.

The estimated box-counting dimension is the slope

\[
D_{\mathrm{build}}
=\frac{d\log N(\epsilon)}{d\log(1/\epsilon)}
\]

obtained by ordinary least squares on a fixed physical interval, by default 50–3200 m. The output includes \(R^2\), slope standard error, scale-span in decades, dispersion across grid origins and leave-one-scale-out stability.

This is a finite-range scaling exponent. It is not asserted to be an asymptotic Hausdorff dimension.

## 3. Domain-aware lacunarity

For a moving window \(W\) of side \(s\), define the occupied mass

\[
S_W=\sum_{(i,j)\in W}M_{ij}
\]

and the number of domain cells

\[
D_W=\sum_{(i,j)\in W}\Omega_{ij}.
\]

Only windows satisfying \(D_W/|W|\ge f_{\min}\) are retained. With the default \(f_{\min}=0.95\), edge windows dominated by exterior bounding-box pixels are rejected. Lacunarity is

\[
\Lambda(s)=\frac{\operatorname{Var}(S_W)}{\operatorname{E}(S_W)^2}+1.
\]

## 4. Minkowski dilation and digital topology

For radius \(r\), the clipped dilation is

\[
M_r=\{x\in\Omega:\operatorname{dist}(x,M)\le r\}.
\]

On every sampled radius the program reports:

- occupied area \(A(r)\);
- Crofton perimeter \(P(r)\);
- \(\beta_0(r)\), the number of connected foreground components;
- \(\beta_1(r)\), the number of holes relative to the irregular domain boundary;
- Euler characteristic \(\chi(r)=\beta_0(r)-\beta_1(r)\);
- largest-component fraction.

Digital topology uses a dual connectivity pair: if the foreground uses 4-neighbour connectivity, the background uses 8-neighbour connectivity, and conversely. This avoids simultaneous contradictory foreground/background connections at diagonal contacts.

### 4.1 Giant-component radius

Let \(C_{\max}(r)\) be the largest foreground component and \(|M_r|\) the occupied-cell count. For threshold \(g\), default \(g=0.5\),

\[
r_g=\inf\left\{r:\frac{|C_{\max}(r)|}{|M_r|}\ge g\right\}.
\]

This is a giant-component transition, not a boundary-percolation threshold.

### 4.2 Directional spanning and disconnected boundaries

A connected foreground label spans left–right if it intersects both left and right boundary bands; top–bottom is defined analogously.

Version 0.4.1 reports two definitions:

1. **full-domain bounding-box spanning**: bands are tied to extrema of the complete analysis domain;
2. **main-component spanning**: bands are tied to extrema of the largest connected component of the domain.

If the administrative domain is disconnected, whole-domain spanning is generally not interpretable because dilation is clipped to disconnected components. In that case the main-component value is reported as the recommended core-city descriptor, while the full-domain result is retained for transparency. The output records the domain component count and the area fraction of the largest component.

### 4.3 Integrated topology descriptors

The legacy raw descriptors are

\[
I_{\mathrm{arch,raw}}=\int \beta_0(r)\,d\log r,
\]

\[
I_{\mathrm{void,raw}}=\int \beta_1(r)\,d\log r,
\]

\[
I_{\mathrm{bdry,raw}}=\int P(r)\,d\log r.
\]

They depend on the sampled radius interval and, respectively, on component count or city length scale. Therefore they must not be used directly for inter-city clustering.

For \(\Delta\log r=\log(r_{\max}/r_{\min})\), initial component count \(N_0=\beta_0(0)\), domain area \(A_\Omega\), and characteristic length \(L_c=\sqrt{A_\Omega}\), version 0.4.1 additionally reports

\[
\widehat I_{\mathrm{arch}}
=\frac{1}{N_0\,\Delta\log r}
\int \beta_0(r)\,d\log r,
\]

\[
\widehat I_{\mathrm{void}}
=\frac{1}{N_0\,\Delta\log r}
\int \beta_1(r)\,d\log r,
\]

\[
\widehat I_{\mathrm{bdry}}
=\frac{1}{L_c\,\Delta\log r}
\int P(r)\,d\log r.
\]

These are dimensionless or size-reduced descriptors, but they remain tied to each city’s sampled interval. Dividing by \(\Delta\log r\) does not by itself make different intervals equivalent.

For atlas post-processing, the radius is transformed to

\[
\rho=\frac{r}{\sqrt{A_\Omega}}.
\]

Across all quality-eligible cities the software finds the common interval \([\rho_{\min},\rho_{\max}]\) given by the intersection of available positive-radius coverage. It then interpolates each normalized profile in \(\log\rho\) and computes

\[
I_{\mathrm{arch}}^{*}
=\frac{1}{\Delta\log\rho}
\int_{\rho_{\min}}^{\rho_{\max}}
\frac{\beta_0(\rho)}{\beta_0(0)}\,d\log\rho,
\]

\[
I_{\mathrm{void}}^{*}
=\frac{1}{\Delta\log\rho}
\int_{\rho_{\min}}^{\rho_{\max}}
\frac{\beta_1(\rho)}{\beta_0(0)}\,d\log\rho,
\]

\[
I_{\mathrm{bdry}}^{*}
=\frac{1}{\Delta\log\rho}
\int_{\rho_{\min}}^{\rho_{\max}}
\frac{P(\rho)}{\sqrt{A_\Omega}}\,d\log\rho.
\]

These harmonized descriptors, not the raw or own-interval integrals, are used as topology features in atlas clustering.

## 5. Multifractal analysis

A non-negative raster field defines a finite measure \(\mu\). At scale \(\epsilon\), let \(m_i(\epsilon)\) be the mass in box \(i\) and

\[
p_i(\epsilon)=\frac{m_i(\epsilon)}{\sum_jm_j(\epsilon)}.
\]

Zero-mass boxes are excluded from moment sums. The raster is zero-padded rather than cropped, and probabilities are renormalized independently at each scale.

For \(q\ne1\),

\[
Z_q(\epsilon)=\sum_i p_i(\epsilon)^q,
\qquad
\tau(q)=\frac{d\log Z_q}{d\log\epsilon},
\qquad
D_q=\frac{\tau(q)}{q-1}.
\]

For \(q=1\),

\[
D_1=\frac{d\sum_i p_i(\epsilon)\log p_i(\epsilon)}{d\log\epsilon}.
\]

### 5.1 Two measures, not one replacement

Version 0.4.1 reports two different measures:

- **footprint-area measure**: \(m_{ij}=M_{ij}\). Summed within a box, this is proportional to occupied footprint area. A binary raster is therefore a valid uniform measure on the occupied cells; it is not mathematically invalid merely because its finest-scale values are 0 or 1.
- **height-weighted built-form measure**: \(m_{ij}=H_{ij}M_{ij}\), where \(H_{ij}\) is the rasterized building height. Equal cell area cancels during probability normalization. This is not an exact volume field because fractional building coverage within a pixel is not evaluated.

The two spectra answer different questions and are stored separately. Height-weighted spectra are model-dependent where OSM heights are absent and the configured default height is substituted.

### 5.2 Quality control for \(D_q\)

For an exact probability measure, generalized dimensions are non-increasing in \(q\):

\[
q_1<q_2\quad\Rightarrow\quad D_{q_1}\ge D_{q_2}.
\]

Finite-scale estimates can violate exact ordering because each \(D_q\) is obtained from a noisy regression. Version 0.4.1 therefore does not use a machine-precision threshold. Adjacent fitted dimensions are considered consistent with monotonicity when

\[
D_{q_{i+1}}-D_{q_i}
\le
2\sqrt{\sigma_i^2+\sigma_{i+1}^2},
\]

where \(\sigma_i\) is the standard error of \(D_{q_i}\), obtained from the fitted slope error by \(\sigma_{D_q}=\sigma_{\tau}/|q-1|\) for \(q\ne1\); for \(q=1\) the fitted slope is \(D_1\) itself. The principal atlas check uses orders with \(q\ge0\) whose scaling fit passes the configured \(R^2\) threshold. A separate full-fitted-spectrum diagnostic includes negative orders. Negative \(q\) strongly emphasizes low-mass boxes and is unstable for sparse finite rasters even when a simple regression has an apparently acceptable \(R^2\); those values remain diagnostic and are not admitted automatically to atlas features.

For atlas-level statistics, the conservative default is to use well-fitted non-negative orders, with \(D_0,D_1,D_2\) as the principal triplet, retain negative orders only as diagnostics, and treat height-weighted results separately from footprint-area results.

## 6. Approximate 2.5D building geometry

Each building footprint is treated as a vertical prism with assigned height \(h_k\). Unions of all footprints present above each height level are used so overlapping polygons and shared internal walls are not double-counted.

For successive height levels \(h_j>h_{j+1}\), with union area \(A_j\) and perimeter \(P_j\),

\[
V=\sum_j A_j(h_j-h_{j+1}),
\qquad
A_{\mathrm{wall}}=\sum_j P_j(h_j-h_{j+1}).
\]

The exposed roof is the accumulated increase of union area as lower layers are added. The thermal envelope is

\[
A_{\mathrm{env}}=A_{\mathrm{roof,thermal}}+A_{\mathrm{wall}},
\]

whereas the closed geometric surface used for isoperimetric compactness is

\[
A_{\mathrm{closed}}=A_{\mathrm{roof,geom}}+A_{\mathrm{wall}}+A_{\mathrm{ground}}.
\]

The closed-surface compactness is

\[
C_{3D}=\frac{36\pi V^2}{A_{\mathrm{closed}}^3}.
\]

## 7. Two-phase stationary transport

The transport block solves

\[
\nabla\cdot(k(\mathbf x)\nabla u)=0
\]

on the irregular raster domain using a finite-volume discretization and harmonic interface conductivities. Separate runs treat open space or buildings as the high-conductivity phase, with left–right and top–bottom Dirichlet excitation.

For unit potential difference \(\Delta u=1\), total flux is the effective conductance \(G\), and

\[
\mathcal D_{\Delta u=1}=\int_\Omega k|\nabla u|^2\,dA=G.
\]

For unit total flux, the dissipation equals resistance

\[
R=G^{-1},\qquad \mathcal D_{Q=1}=R.
\]

The discrepancy between boundary flux and volume dissipation is stored as an energy-identity diagnostic. These quantities characterize a model PDE response of the morphology; they are not measurements of actual urban heat or entropy production.

## 8. Requirements for inter-city comparison

A descriptor is admitted to atlas-level comparison only when its own quality conditions are met. In particular:

- the raster area error and boundary area error must pass;
- the box-counting fit must have sufficient points, span and origin/leave-one-out stability;
- topology comparisons must use a harmonized radius interval;
- disconnected-domain spanning must use the explicitly selected definition;
- multifractal orders must pass their scaling fit and uncertainty-aware consistency checks;
- height-weighted and 2.5D features require adequate height completeness and sensitivity reporting;
- transport features require convergence and the energy-identity check.
