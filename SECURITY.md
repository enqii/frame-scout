# Security policy

FrameScout is a local prototype: it reads photo folders on your own computer and runs
its user interface (the Streamlit app and the evaluation tool's labelling page) on
`http://127.0.0.1` only. It has no cloud upload and no online-service integration; the
only network access is the download of packages and model weights on first use.
Security issues still matter, for example
a way for another web page or program to reach the local interface, or a path that lets
a profile or setting read or delete files outside the folders you chose.

## Reporting a vulnerability

Please report it privately through GitHub's
[private vulnerability reporting](https://github.com/enqii/frame-scout/security/advisories/new)
("Security" tab → "Report a vulnerability"), not in a public issue or pull request.
Include the steps to reproduce it and the FrameScout commit you tested.

This is a personal project without guaranteed response times; reports are answered as
soon as possible.

## Supported versions

FrameScout is a prototype. Only the current state of `main` and the latest release
([v1.1.0](https://github.com/enqii/frame-scout/releases/tag/v1.1.0), a pre-release) are
supported; fixes land in `main` and are published with the next release. Older releases
are not patched.
