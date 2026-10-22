# Third-Party Notices

## Upstream project

This repository originated as a fork of [Omada SAML to OIDC Bridge](https://github.com/Snuffy2/omada-saml-oidc) and has since been substantially modified. The upstream project is licensed under the MIT License. This project retains the MIT license text in [LICENSE](LICENSE). The upstream project is not affiliated with or endorsing this fork.

## Runtime dependencies

Python runtime dependencies are declared in `pyproject.toml`. Their installed distributions retain license files in their `.dist-info/licenses/` metadata where provided. Debian packages installed by the image build retain package copyright and license notices under `/usr/share/doc/<package>/copyright` where provided.

Third-party components remain subject to their own license terms. Consult the notices included in the image and the metadata of the exact resolved package versions when redistributing it. Dependency versions can vary between image builds because a dependency lockfile is not committed.
