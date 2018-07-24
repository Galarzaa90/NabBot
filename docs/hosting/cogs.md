# Cogs
You can make your own Cogs to add extra features or commands to NabBot, without having to edit the original files.

This allows you to easily update NabBot when a new version is released, without losing any changes you have made yourself.

To add a cog, you need to place the python file in the `extras` folder (or anywhere actually), and then add a reference to it in config.yml, like:

```yaml
extra_cogs:
  - extra.example
```

This will load the cog in `extras/example.py`.

Cogs can access to methods, variables and constants in `nabbot.py` (inside the NabBot class) and the python files in `utils/`.

This is still an experimental feature, so use under your own risk.