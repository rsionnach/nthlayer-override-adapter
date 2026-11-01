# Changelog

## [0.3.0](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.14...v0.3.0) (2026-11-01)


### ⚠ BREAKING CHANGES

* the adapter's span is renamed gen_ai.override -> nthlayer.reversal, and its attributes move from gen_ai.override.* to nthlayer.reversal.*: reviewer -> actor, corrected_action -> new_value, decision_id, reason, service, original_action, confidence_at_decision and source_system keep their names under the new prefix, and nthlayer.reversal.type=human_override and nthlayer.reversal.actor_type=human are added. The free-text reason is no longer put on the span by default: set privacy.emit_reason_on_span: true to keep it (core still stores it either way; exclude_reason still drops it everywhere). Update any collector filter, spanmetrics config or trace query keyed on the old span or attribute names.

### Bug Fixes

* emit overrides as an nthlayer.reversal span; reason opt-in (opensrm-1dua) ([6d0dbbf](https://github.com/rsionnach/nthlayer-override-adapter/commit/6d0dbbfe48aac7038bceefb79c356c15d36fd8ad))
* require nthlayer-common 5.9.1 ([1d35181](https://github.com/rsionnach/nthlayer-override-adapter/commit/1d35181f2316c555b580c897d11078f831e93abb))
* require nthlayer-common 5.9.1 ([400508f](https://github.com/rsionnach/nthlayer-override-adapter/commit/400508fe16bb5c887dabf1722241094235a7aba4))
* the override span is nthlayer.reversal, with A1 attribute names (opensrm-1dua) ([a9a9125](https://github.com/rsionnach/nthlayer-override-adapter/commit/a9a91258499da26147b98c45fdc7ec40b272c71a))

## [0.2.14](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.13...v0.2.14) (2026-11-01)


### Bug Fixes

* require nthlayer-common 5.9.0 ([7b4dec7](https://github.com/rsionnach/nthlayer-override-adapter/commit/7b4dec786f69548e7718471e4da5476763db5518))
* require nthlayer-common 5.9.0 ([804ce40](https://github.com/rsionnach/nthlayer-override-adapter/commit/804ce4024c586d52faad76b86b9fcfa666c45389))

## [0.2.13](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.12...v0.2.13) (2026-10-31)


### Bug Fixes

* require nthlayer-common 5.8.1 ([8ebcaf6](https://github.com/rsionnach/nthlayer-override-adapter/commit/8ebcaf699e4579d400935615de43dd2b40c1601c))
* require nthlayer-common 5.8.1 ([8370992](https://github.com/rsionnach/nthlayer-override-adapter/commit/83709926775d78cb3ff1e017c945a1f8909948c2))

## [0.2.12](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.11...v0.2.12) (2026-10-31)


### Bug Fixes

* ship the Apache-2.0 LICENSE and declare it in package metadata (opensrm-bqfj) ([f71185b](https://github.com/rsionnach/nthlayer-override-adapter/commit/f71185bf576f69389ec6ee3bfba39f5b1b68174d))
* ship the Apache-2.0 LICENSE and declare it in package metadata (opensrm-bqfj) ([214d81a](https://github.com/rsionnach/nthlayer-override-adapter/commit/214d81a5a63ed3005f081673f4411b89dad371d3))

## [0.2.11](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.10...v0.2.11) (2026-10-29)


### Bug Fixes

* require nthlayer-common 5.8.0 (opensrm-wo62.4.13) ([7b13418](https://github.com/rsionnach/nthlayer-override-adapter/commit/7b13418e29e7f75e6778314517e2321e64987736))
* require nthlayer-common 5.8.0 (opensrm-wo62.4.13) ([7689875](https://github.com/rsionnach/nthlayer-override-adapter/commit/76898750ca21cef3db3de77848b616d20587a931))

## [0.2.10](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.9...v0.2.10) (2026-10-28)


### Bug Fixes

* require nthlayer-common 5.6.0 (opensrm-wo62.4.1) ([7378feb](https://github.com/rsionnach/nthlayer-override-adapter/commit/7378feb1a3ce0435d3496c7a52ba65e232004836))
* require nthlayer-common 5.6.0 (opensrm-wo62.4.1) ([389f82b](https://github.com/rsionnach/nthlayer-override-adapter/commit/389f82b923178849bd8bc6ec41096ae173a13402))
* require nthlayer-common 5.7.0 (opensrm-wo62.4.7) ([76b9b9c](https://github.com/rsionnach/nthlayer-override-adapter/commit/76b9b9cf8898afaaf9185e06d96130d1d53b4841))
* require nthlayer-common 5.7.0 (opensrm-wo62.4.7) ([d5bab43](https://github.com/rsionnach/nthlayer-override-adapter/commit/d5bab4304d9781bd0f57fa4a381260398617bf1c))

## [0.2.9](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.8...v0.2.9) (2026-10-27)


### Dependencies

* require nthlayer-common 5.5.0 (opensrm-wo62.1) ([fa78ab2](https://github.com/rsionnach/nthlayer-override-adapter/commit/fa78ab25a40d0e9d962b49292daef43b6e6cadbb))

## [0.2.8](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.7...v0.2.8) (2026-10-24)


### Dependencies

* require nthlayer-common 5.4.0 (opensrm-wo62.1) ([c17646b](https://github.com/rsionnach/nthlayer-override-adapter/commit/c17646be33c570616da9058bda46809c3b89aa10))

## [0.2.7](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.6...v0.2.7) (2026-10-23)


### Dependencies

* require nthlayer-common 5.3.1 (opensrm-dww5) ([67b87aa](https://github.com/rsionnach/nthlayer-override-adapter/commit/67b87aa1cc314f0e44504672678112ec8126a6af))

## [0.2.6](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.5...v0.2.6) (2026-10-23)


### Dependencies

* require nthlayer-common 5.3.0 (opensrm-pnmv) ([5497df0](https://github.com/rsionnach/nthlayer-override-adapter/commit/5497df0a0ebfb019b2be82db130de3e5e36f659b))

## [0.2.5](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.4...v0.2.5) (2026-10-21)


### Dependencies

* require nthlayer-common 5.2.0 (opensrm-g35i) ([e5fbfe2](https://github.com/rsionnach/nthlayer-override-adapter/commit/e5fbfe25da6a0e5f953e089bf6a96c9339cf50bd))

## [0.2.4](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.3...v0.2.4) (2026-10-12)


### Dependencies

* require nthlayer-common 5.0.0 (opensrm-7zpz) ([bdf493c](https://github.com/rsionnach/nthlayer-override-adapter/commit/bdf493cc92f8eb8c16f9d1af929c93a88ddf2e90))

## [0.2.3](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.2...v0.2.3) (2026-10-11)


### Dependencies

* require nthlayer-common 4.0.0 (opensrm-4zdc) ([44a00c5](https://github.com/rsionnach/nthlayer-override-adapter/commit/44a00c5f37bc8adb1deedbf8350aeabe61ba285a))

## [0.2.2](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.1...v0.2.2) (2026-10-06)


### Bug Fixes

* **deps:** declare compatibility with nthlayer-common 3.0.0 ([5a938cb](https://github.com/rsionnach/nthlayer-override-adapter/commit/5a938cbae9233c891e885d3da8370c62396d4751))
* **deps:** declare compatibility with nthlayer-common 3.0.0 ([6b5594e](https://github.com/rsionnach/nthlayer-override-adapter/commit/6b5594e17d6b56a05b81d3e0eb7a2b59f0f280a6))

## [0.2.1](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.2.0...v0.2.1) (2026-09-27)


### Bug Fixes

* declare the nthlayer-common range this repo is actually tested against ([0e43e3f](https://github.com/rsionnach/nthlayer-override-adapter/commit/0e43e3f1ba3fa94899fed241f6e8a9a9adb68a20))
* declare the nthlayer-common range this repo is actually tested against (opensrm-p3bm) ([67c9dc6](https://github.com/rsionnach/nthlayer-override-adapter/commit/67c9dc6ccf658036ed6c9fb0b243261f1e4bde77))


### Documentation

* add contributing guide (opensrm-tu04.4) ([4f5bad9](https://github.com/rsionnach/nthlayer-override-adapter/commit/4f5bad9a03fcb60de34fb3404cdfab9f5283d191))

## [0.2.0](https://github.com/rsionnach/nthlayer-override-adapter/compare/v0.1.0...v0.2.0) (2026-06-24)


### Features

* **app:** wire CoreAPIClient lifecycle + observable absent-guard · opensrm-jmy.18 ([8bc7ee5](https://github.com/rsionnach/nthlayer-override-adapter/commit/8bc7ee5ff018003ba104b219d0605f56d1ba72b9))
* **config:** add required core block (url + timeout_seconds) · opensrm-jmy.18 ([8f4d1cd](https://github.com/rsionnach/nthlayer-override-adapter/commit/8f4d1cd0ba68da574a00fec0b2848abea2edb4ac))
* **emission:** add bind_to_core helper · opensrm-jmy.18 ([ea45aca](https://github.com/rsionnach/nthlayer-override-adapter/commit/ea45acafd87532e9ea551f3cfd4fa5640f6f2203))
* **metrics:** add nthlayer_override_binding_total · opensrm-jmy.18 ([69a10dd](https://github.com/rsionnach/nthlayer-override-adapter/commit/69a10dd3d8f22df677e3214e61b072c3b69dacef))
* **routes:** wire bind_to_core into canonical batch · opensrm-jmy.18 ([c364903](https://github.com/rsionnach/nthlayer-override-adapter/commit/c364903699445656b8b22ce41f773ca934c2f13b))
* **routes:** wire bind_to_core into canonical single · opensrm-jmy.18 ([e379ecb](https://github.com/rsionnach/nthlayer-override-adapter/commit/e379ecb565628199de82f99e35e8d86bb1b87b68))
* **routes:** wire bind_to_core into webhook · opensrm-jmy.18 ([a0c3427](https://github.com/rsionnach/nthlayer-override-adapter/commit/a0c34276badac7e75dc5cc9f8869e648a3dbc803))


### Bug Fixes

* **privacy:** apply privacy once at sidecar boundary · opensrm-jmy.18 ([740b898](https://github.com/rsionnach/nthlayer-override-adapter/commit/740b898f48da4da6e7cb744e5370d0cfab9dc128))


### Documentation

* **CLAUDE.md:** catch up auto-memory drift from prior bead sessions ([1c9faa6](https://github.com/rsionnach/nthlayer-override-adapter/commit/1c9faa68291d2343209ef0ea9e8d375a71fa7821))
* **CLAUDE.md:** record jmy.18 sidecar additions · opensrm-jmy.18 ([da60927](https://github.com/rsionnach/nthlayer-override-adapter/commit/da60927951983712cf830bdc138a110ba9e84978))
* link to ecosystem testing conventions (opensrm-2wkc) ([13ed8f4](https://github.com/rsionnach/nthlayer-override-adapter/commit/13ed8f4d8b98f101407fb928effea7f76703af18))
* thin CLAUDE.md; move detail to AGENTS.md + docs/ ([40720a0](https://github.com/rsionnach/nthlayer-override-adapter/commit/40720a0e25ca12b6b30cbaad0ccd5aa9bb812974))
