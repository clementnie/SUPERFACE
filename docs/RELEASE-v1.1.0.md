# SUPERFACE v1.1.0 acceptance and provenance

The release reuses the physically accepted Phase 8.1 artifacts. No firmware,
font or host executable was rebuilt during publication, and no hardware or
installed Linux configuration was changed.

## Source correspondence

The sealed build revision is `6f5a4dd08d78b8b0fd8a28ff46be099890a02f2a`.
The final implementation revision is `43ae05f` (adds the installed layout
utility and its installer checks). The subsequent `1902b25` commit records
physical results. The v1.1.0 publication commit only updates documentation,
licensing and release evidence. FPGA/host implementation sources and font data
are unchanged from the accepted versions. Every packaged service script and
notice was compared byte-for-byte with the corresponding accepted source.

The ARM64 binaries match the hashes in the archived native-host acceptance log:

```text
9c0f84abb73c6dfcfd019b1942c5dfe782f15376e50990fc7e08140dfa7fbe8e  host/build/superface
0315a77196a2d642181d763c4077299a304d8e67be3b635550ac8af49c36f760  host/build/superface-uart
```

## Accepted artifacts

```text
67682faa8600cb04e1dabdb7c280a1a5ff2a8dcdcdcd36d1f0b94706fc3f6d6f  LAB8.sof
77a9082c7b01ff16a7609945e733f2c08fe3a7eb87a3ff7296e32a593291b7aa  LAB8-EPCS4.pof
3f1425824d6e2bea955687cdaf9ef88e4c8f6600363fb3d9c1b4e608e6f90243  superface-linux-arm64.tar.gz
f453aeb01d875ffd88e73822cb848d4dff87c6c1ca024dbf515460f7bb45fd0f  superface_font.bin
373f840cd48570c79eff9f8706ccb44e220cd27f63c57818d0ba72bc444f2314  font_manifest.json
fa474ce2216d13d42cab9638c2541ab0730aa31283ece0e7e1e0c7b6955eab95  glyph_map.csv
```

The release's `SHA256SUMS` covers every attached payload, including the explicit
source archive and unchanged font license archive. The font image and manifests
also match the source tree byte-for-byte. The accepted-source revision attachment
identifies the original build, rather than the later publication commit.

## Acceptance

Quartus II 13.0 SP1 fit and timing summaries and the physical UART benchmark
are attached to the release. The fit uses 5,197 logic elements, 2,655 registers,
50 M4Ks, 148,128 memory bits, 155 pins and one PLL on EP2C20F484C7.
Setup slack: +4.362 ns (65 MHz pixel), +6.212 ns (50 MHz), +30.633 ns (24 MHz).
Worst fast-model hold slack: +0.215 ns. Gray-pointer routes meet 10 ns bounds.
The inherited SW[0] lab clock warning remains.

Operator acceptance covered XGA synchronization, 80 × 30 geometry, Colemak,
Caps Lock-to-Backspace, Chinese, Unicode graphics and application responsiveness.
EPCS4 programming and verification succeeded; a final device Verify also passed.
The operator confirmed production deployment and standalone physical cold boot
before this publication resumed. The subsequent recovery reboot also preserved
terminal operation. These operator statements are acceptance evidence, not a new
publication-time hardware test. The UART benchmark measured 16.66 / 16.48 /
49.92 / 49.88 ms for single-cell / multiline / full-screen / clear visible ACKs,
and 60.01 Hz for four-row coherent sparse updates. That sparse rate is not an
arbitrary full-screen frame rate. See [verification](VERIFICATION.md).

The independent [v1.0.0 rollback release](https://github.com/clementnie/SUPERFACE/releases/tag/v1.0.0)
and its tag are preserved without rewriting history.
