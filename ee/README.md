# ee/ — Eva Enterprise Edition (submodule)

This directory is a git submodule pointing to the private repo `hop-top/eva-ee`.

## For CE contributors

No action needed. `ee/` may appear empty — that is expected.
CE core, server, CLI, and plugins do not require EE code.

## For EE contributors

Requires read access to `hop-top/eva-ee`. Request via: hi@hop.top

Populate the submodule after cloning:

```
git submodule update --init
```

Confirm contents:

```
ls ee/
# server/  plugins/  tests/  docs/  pyproject.toml  LICENSE
```

## License

EE code is licensed under Business Source License 1.1.
See `ee/LICENSE` (populated after submodule init) for terms.
Change Date: 2030-03-09 → Apache-2.0.
