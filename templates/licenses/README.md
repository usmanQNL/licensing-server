# License templates

The add-licensing skill copies these files into a target project. The standard licenses are kept word for word; only the `<...>` placeholders change. Never edit the terms of a standard license. If a project needs different terms, it needs a different license.

This is not legal advice. The standard licenses below are widely used and safe to copy as they are. The EULA template is a starting point and should be reviewed by a lawyer before anyone sells under it.

## Placeholders

| Placeholder | Fill with |
|---|---|
| `<YEAR>` | the year of first publication, for example `2026` |
| `<COPYRIGHT HOLDER>` | the person or company that owns the code |
| `<APP NAME>` | the application name from Step 1 |
| `<LICENSE NAME>` | the license's full name, for example `MIT License` |
| `<CONTACT EMAIL OR SALES PAGE>` and other `<...>` | as the placeholder says |

## Free projects (OpenSource mode)

Pick one code license. MIT is the default.

| SPDX ID | Template | Copy to | Notes |
|---|---|---|---|
| `MIT` | `open-source/MIT.txt` | `LICENSE` | Shortest, most used. Keep the copyright line. |
| `Apache-2.0` | `open-source/Apache-2.0.txt` and `open-source/Apache-2.0-NOTICE.txt` | `LICENSE` and `NOTICE` | Adds an explicit patent grant. The LICENSE text has no placeholders; the copyright line goes in `NOTICE`. |
| `BSD-2-Clause` | `open-source/BSD-2-Clause.txt` | `LICENSE` | Like MIT. |
| `BSD-3-Clause` | `open-source/BSD-3-Clause.txt` | `LICENSE` | Like BSD-2, and bars using the owner's name to promote derived products. |

### Optional add-ons (any free license)

| Add-on | Template | Copy to | Notes |
|---|---|---|---|
| DCO sign-off | `dco/DCO`, `dco/CONTRIBUTING.md`, `dco/dco.yml` | `DCO`, `CONTRIBUTING.md`, `.github/workflows/dco.yml` | Contributors sign off each commit (`git commit -s`). The workflow fails pull requests with unsigned commits. Copy `DCO` unchanged. |
| Docs and assets: `CC-BY-4.0` | `docs-assets/CC-BY-4.0.txt` | `docs/LICENSE` or `assets/LICENSE` | Reuse with credit. For documentation, images, sounds and other non-code files only. |
| Docs and assets: `CC0-1.0` | `docs-assets/CC0-1.0.txt` | `docs/LICENSE` or `assets/LICENSE` | Public domain dedication. For non-code files only. |

Creative Commons licenses are not meant for software, and Creative Commons says so itself. Never offer them for code. When a project uses one for a folder, add a line to the README such as "Code is MIT; the contents of `docs/` are CC-BY-4.0."

## Paid projects (Subscription and Gated modes)

Pick one. The proprietary EULA is the default.

| Choice | SPDX ID | Template | Copy to | When it fits |
|---|---|---|---|---|
| Proprietary EULA | `LicenseRef-Proprietary` | `paid/LICENSE-proprietary.txt` and `paid/EULA.md` | `LICENSE` and `EULA.md` | Closed or private code sold per seat or by subscription. The EULA's seat, term, grace period and feature terms match what the license file enforces. Needs a lawyer's review. |
| Business Source License 1.1 | `BUSL-1.1` | `paid/BUSL-1.1.txt` | `LICENSE` | Public source; production use needs a paid license (or the Additional Use Grant). Each version turns into the Change License (Apache-2.0 here) on the Change Date, at most four years after release. Fill in the Parameters block; do not change the rest. |
| Elastic License 2.0 | `Elastic-2.0` | `paid/Elastic-2.0.txt` | `LICENSE` | Public source; anyone may use it, but not offer it as a hosted service, and not remove or bypass license keys. Add `Copyright <YEAR> <COPYRIGHT HOLDER>` to the README or a `NOTICE` file. |
| PolyForm Noncommercial 1.0.0 | `PolyForm-Noncommercial-1.0.0` | `paid/PolyForm-Noncommercial-1.0.0.md` | `LICENSE.md` | Public source; free for personal, research and nonprofit use, paid for commercial use. Put `Required Notice: Copyright <YEAR> <COPYRIGHT HOLDER>` at the top, above the license text. |

### Dual licensing

Dual licensing offers the same code under two licenses: a strong copyleft license (usually `AGPL-3.0-only`) for free users, and a paid commercial license for those who can't accept copyleft. There is no template here, because the setup depends on the project:

1. Get the AGPL text from https://www.gnu.org/licenses/agpl-3.0.txt and save it as `LICENSE`, unchanged.
2. Use `paid/LICENSE-proprietary.txt` and `paid/EULA.md` as the commercial license, saved as `COMMERCIAL-LICENSE.txt` and `EULA.md`.
3. Add a README section that says which license applies to whom and how to buy the commercial one.
4. Contributions must allow relicensing, so you need a contributor license agreement (CLA) or copyright assignment. The DCO alone is not enough. Get legal advice for this step.
