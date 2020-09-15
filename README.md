
MooPad - a launch pad for cows
==============================

MooPad started as a project to help cows fly (or at least launch). Because apparently pigs already do. Unfortunately it has since been sidetracked into being a lame script that can run different actions (commands) depending on which files changed in a repository. Useful for monorepos.

TODO
----
- Send to stdout/stderr respectively the result of running actions
- Logger. Log to file in addition to sending to stdout/stderr
- TOML?

Command line arguments
----------------------
- `-c moopad.yaml, --config-file moopad.yaml`  
  Alternative configuration file, YAML format.
- `-d root/dir, --workdir root/dir`  
  Working directory. Defaults to the directory the script was started in. Actions will be executed in this directory unless otherwise specified. The most useful value for this parameter is probably the root of the repository.
- `-f changed.txt, --changes-as-file changed.txt`  
  Path to file containing list of changes, one file per line.
- `-s newline-separated-string, --changes-as-string newline-separated-string`  
  A string containing list of changed files, separated by newlines


Configuration file
------------------

A configuration file can have two types of top-level sections:
- A section named `action_templates`, which defines a list of actions that can be referred to in the other sections (stages).
- Anything else is considered a stage. A stage groups together a set of actions (commands) to run. 

### Stages
A stage is a set of actions that are executed in parallel. If one of them fails (returns an error), the stage fails and execution stops. Later stages depend on the ones before them.

Stages run in alphabetical order. Using names like `10_gather-info`, `20_set-config`, `30_build-it` helps with making clear the order of operations and it means that future stages can be inserted if needed (ex. `05_download-tools`, `25_run-tests`).

Actions within a stage are deduplicated. Actions that end up having the same combination of `run`, `cwd` and `type` after substitution are considered identical and only one of them is executed. The `name` filed is ignored when comparing actions. 

A stage has the following properties:
- `path`: Files that match this value will trigger the defined actions. Matching is done using [shell-style wildcards](https://docs.python.org/3/library/fnmatch.html) (aka "glob patterns").
- `actions`: A list of actions to execute on files that match the `path`.

### Actions
An action describes the command to run and is defined under a stage. It can have the following fields:
- `run`: REQUIRED. The action to run. See `type`. Accepts substitutions.
- `name`: Optional. A name for the action. Can be any string, it is only used for display. Doesn't have to be unique and it is ignored when de-duplicating actions. Accepts substitutions.
- `type`: Optional, defaults to "shell". Defines the type of action. Currently "shell" is the only supported type, which stands for "shell command".
- `cwd`: Optional, defaults to False. Change/current working directory. Can be boolean or string:
  - *False*: default value, the `run` command will be executed in the scripts working directory. See command line options.
  - *True*: before running a command it will change to the directory the changed file is in. So, if the changed file is `src/modules/libfoo/ls.al` it will run the command in `src/modules/libfoo`.
  - *"any/string"*: it will change to the specified directory. Accepts substitutions. Should probably be an absolute path (use *root_dir*). Currently there is no validation on the field before the action is executed.
- `template`: Optional. If defined, the script looks for a template with the corresponding `id` and the two are "merged", with the fields defined here overwriting the ones defined in the template.

#### Substitutions
The `run`, `cwd` and `name` properties accept a few simple substitutions. For example, assuming the changed file is `docs/modules/README.md`, *"grep 'TODO' ${file_name}"* will be replaced with *"grep 'TODO' README.md"*. This will happen before the command is run, so before any shell variables are expanded.

These are the valid substitutions, probably best explained with an example. Assuming a changed file `docs/modules/bartender/README.md`:
- `root_dir`: working directory. See command line arguments.
- `file_path`: full file path (`docs/modules/bartender/README.md`)
- `file_name`: file name (`README.md`)
- `dir_path`: directory path (`docs/modules/bartender`)
- `dir_name`: directory name (`bartender`)
- `parent_dir_path`: parent directory path (`docs/modules`)
- `parent_dir_name`: parent directory name (`modules`)

### Action templates
The `action_templates` section defines a list of templates that can be linked to from stages to make it easier to re-use the same action multiple times.

Example:
```
stage_x:
  - path: "*"
    action:
      - template: echo_date
        name: "dispplay currrent date"
action_templates:
  - id: echo_date
    run: date
    name: "show_date"
    type: shell
    cwd: True
```

A template has the same properties as an action, plus the `id` field, which is used to match actions with templates. Fields defined in the action overwrite the values defined in the template.
