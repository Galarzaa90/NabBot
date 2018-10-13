# Contributing to NabBot
Thanks for your interesting in contributing to NaBot and taking your time to read this.

This document will guide you in how to contribute to the project properly.

## Bug reports
There's multiple ways to report bugs, the preferred way is creating an [issue](https://github.com/NabDev/NabBot/issues).

You can also report bugs by joining our Discord Server: https://discord.gg/NmDvhpY

When reporting a bug, it is important to provide the following:
- How to reproduce the bug:
  - What did you do?
  - If it is a command error, how was it called exactly?
  - If it is on a self-hosted instance of NabBot, what Python version and what NabBot version was used?
- Show evidence of the error:
  - What is shown when the error occurs?
  - If it is a self-hosted instance of NabBot, is there any information printed on the log?
  
## Submitting fixes
You can submit fixes by creating [pull requests](https://github.com/NabDev/NabBot/pulls).

Before submitting a pull request, please check the following:
- The pull request is based on the `dev` branch and not `master`. Unless it is a critical fix.
- Make sure that no new module dependencies were added without updating `requirements.txt`.
- Make sure the changes are compatible with `Python 3.6`, do not use any features introduced in later versions.

## Branching model
NabBot uses the following branching model:

- `master` - This branch contains the latest release, meaning that this version is always stable.
- `dev` - This branch is where new changes are made. Pull requests should point to this branch.
  This branch may contain bugs and incomplete features.
- `feat-*` - Used to implement features that require extended development, to isolate the environment and be able to keep updating the other branches.
- `release-*` - This branch is only used to prepare for releases. Final tests, documentation and version updates are done here before merging into `master`.

![Example Brancing Model](https://nvie.com/img/git-model@2x.png)
