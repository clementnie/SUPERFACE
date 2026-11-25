# Licensing

Original SUPERFACE code and documentation in v1.1.0 and v1.2.0 are distributed under
**GPL-2.0-only**; see [LICENSE](LICENSE). This does not grant a license to
third-party material under GPL or replace its existing terms.

The earlier MIT grant and copyright notice are preserved in
[LICENSES/SUPERFACE-MIT.txt](LICENSES/SUPERFACE-MIT.txt). Previously published
MIT versions remain available under that grant. The accepted v1.1.0 ARM64
archive was redistributed unchanged, including its original MIT notice; the
matching original project source is also available under GPL-2.0-only.

| Material | Applicable terms |
| --- | --- |
| Original SUPERFACE host code, protocol/control modules, tools and documentation | GPL-2.0-only; preserve the earlier MIT notice where present |
| libvterm, statically linked into the ARM64 host | [Upstream MIT notice](host/deps/libvterm-LICENSE.txt), retained in the host archive |
| Fusion Pixel and derived font artwork | [Bundled font notices](assets/fonts/LICENSES): Fusion Pixel, Ark Pixel, Cubic 11 and Galmuri; retain each upstream notice and font license |
| GNU Unifont fallback bitmaps | Upstream SIL OFL 1.1 option for font artwork, with upstream README, OFL and GPL notices in [the font licenses](assets/fonts/LICENSES/unifont) |
| Unihan repertoire data used to select Han scalars | [Unicode data license](assets/fonts/LICENSES/unicode/LICENSE.txt) |
| Quartus-generated support files and device programming collateral | Their embedded Altera/vendor notices and applicable tool/IP terms; no GPL relicensing is claimed |
| Pre-existing lab circuits and baseline ASCII bitmap | Their existing terms and provenance are preserved; no third-party authorship or relicensing is claimed |

The repository and release are a collection with multiple licenses. In
particular, the original-code GPL declaration does not replace vendor terms
for generated IP or font licenses. Keep these notices with redistributed
source, executables, programming files and font assets as applicable.
