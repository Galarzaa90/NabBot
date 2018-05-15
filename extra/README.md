# Extra Cogs
This folder contains an example of an extra cog.

The idea is to let you add your own cogs to add more commands or more features to the bot, without having to edit the original files.

This allows you to easily update NabBot when a new version is released, without losing any changes you have made yourself.

To add a cog, you need to place the python file here (or anywhere actually), and then add a reference to it in config.yml, like:

```yaml
extra_cogs:
  - extra.example
```

This will load the cog in `extra/example.py`.

Cogs can access to methods, variables and constants in `nabbot.py` (inside the NabBot class) and the python files in `utils/`.

This is still an experimental feature, so use under your own risk.