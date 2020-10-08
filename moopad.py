#!/usr/bin/env python3
import subprocess
import sys
import yaml
from argparse import ArgumentParser
from fnmatch import fnmatch
from os import getcwd
from pathlib import PurePath, Path
from pprint import pprint
from string import Template


def build_action(
    changed_file: str,
    matched_path: str,
    path_action: dict,
    root_dir: str,
    action_templates: list = [],
):
    """'Compiles' an action to its final form, ready to be executed.

    Args:
        changed_file (str): Path to the file that was changed which
            would trigger this action.
        matched_path (str): The path in config file that is a match for
            the changed file and would trigger the action
        path_action (dict): Action to take as defined under "actions" in
            the config file. This could be a full action or just the id
            of a template.
        root_dir (dict):
        action_templates (list, optional): Full list of action templates
            as defined in the config file. Defaults to [].

    Returns:
        dict: the action to execute
    """
    action = path_action.copy()
    # Default action type is "shell"
    if "type" not in action:
        action["type"] = "shell"
    # Search for the action template specified. If found, merge the
    # two actions, with the active action overwriting the template
    if path_action.get("template", False):
        for action_template in action_templates:
            if action_template["id"] == path_action["template"]:
                action = {**action_template, **path_action}
                break
    # substitute macros in action's command
    ppath_root_dir = PurePath(root_dir)
    ppath_file = PurePath(changed_file)
    root_dir = str(ppath_root_dir)
    if ppath_file.is_absolute():
        file_path = str(ppath_file)
        dir_path = str(ppath_file.parent)
        parent_dir_path = str(ppath_file.parent.parent)
    else:
        file_path = str(ppath_root_dir.joinpath(ppath_file))
        dir_path = str(ppath_root_dir.joinpath(ppath_file.parent))
        parent_dir_path = str(ppath_root_dir.joinpath(ppath_file.parent.parent))
    file_name = ppath_file.name
    dir_name = ppath_file.parent.name
    parent_dir_name = ppath_file.parent.parent.name
    action_run = Template(action["run"])
    action["run"] = action_run.substitute(
        root_dir=root_dir,
        file_path=file_path,
        file_name=file_name,
        dir_path=dir_path,
        dir_name=dir_name,
        parent_dir_path=parent_dir_path,
        parent_dir_name=parent_dir_name,
    )
    # substitute macros in working directory
    if "cwd" not in action or action["cwd"] is False:
        action["cwd"] = root_dir
    elif action["cwd"] is True:
        action["cwd"] = dir_path
    else:
        action_cwd = Template(action["cwd"])
        action["cwd"] = action_cwd.substitute(
            root_dir=root_dir,
            file_path=file_path,
            file_name=file_name,
            dir_path=dir_path,
            dir_name=dir_name,
            parent_dir_path=parent_dir_path,
            parent_dir_name=parent_dir_name,
        )
    # set a placeholder name if not set
    if "name" not in action:
        action["name"] = action["run"].split()[0]
    else:
        action_name = Template(str(action["name"]))
        action["name"] = action_name.substitute(
            root_dir=root_dir,
            file_path=file_path,
            file_name=file_name,
            dir_path=dir_path,
            dir_name=dir_name,
            parent_dir_path=parent_dir_path,
            parent_dir_name=parent_dir_name,
        )
    return action


def deduplicate_actions(actions: list):
    """Returns a list of actions that contains no identical elements

    Two actions are considered identical if they have the same "run",
    "cwd" and "type" properties. "name" is ignored.

    The returned list is not ordered and it's not guaranteed that it
    will preserve the original ordering.
    """
    total_number_of_actions = len(actions)
    final_list = []
    while len(actions) != 0:
        final_list.insert(0, actions.pop())
        i = 0
        while i < len(actions):
            if (
                actions[i]["run"] == final_list[0]["run"]
                and actions[i]["cwd"] == final_list[0]["cwd"]
                and actions[i]["type"] == final_list[0]["type"]
            ):
                actions.pop(i)
            else:
                i = i + 1
    # Change the original actions list, to be consistent with
    # run_actions().
    actions.extend(final_list)
    # Return number of actions removed. For some reason.
    return total_number_of_actions - len(actions)


def run_actions(actions: list):
    # TODO: limit the number of processes executed at once
    # TODO: consider action type. All actions are of type "shell" now
    for idx, action in enumerate(actions):
        actions[idx]["process"] = subprocess.Popen(
            action["run"],
            cwd=action["cwd"],
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding=sys.stdout.encoding,
        )
    great_success = True
    for idx, action in enumerate(actions):
        actions[idx]["stdout"], actions[idx]["stderr"] = action["process"].communicate()
        actions[idx]["returncode"] = action["process"].returncode
        # TODO: allow different conditions for success. for now,
        #       success means returncode = 0
        if action["process"].returncode != 0:
            actions[idx]["executed_successfully"] = False
            great_success = False
        else:
            actions[idx]["executed_successfully"] = True
        actions[idx]["pid"] = action["process"].pid
        del actions[idx]["process"]
    return great_success


def run_stage(
    stage_cfg: list, changed_files: list, working_dir: str, action_templates: list
):
    actions = []
    for changed_file_path in changed_files:
        for path_cfg in stage_cfg:
            if not fnmatch(name=changed_file_path, pat=path_cfg["path"]):
                continue
            for path_action in path_cfg["actions"]:
                actions.append(
                    build_action(
                        changed_file=changed_file_path,
                        matched_path=path_cfg["path"],
                        path_action=path_action,
                        action_templates=action_templates,
                        root_dir=working_dir,
                    )
                )
    deduplicate_actions(actions)
    actions_ran_successfully = run_actions(actions)
    return actions_ran_successfully, actions


def main(config_file: str, changed_files: list, working_dir: str):
    with open(config_file) as cfg_file:
        cfg = yaml.safe_load(cfg_file)
    action_templates = cfg.get("action_templates", [])
    stages = sorted(cfg.keys(), key=str.lower)
    # "action_templates" is not a stage. Note that it is case sensitive.
    try:
        stages.remove("action_templates")
    except ValueError:
        pass
    for stage in stages:
        stage_success, stage_actions = run_stage(
            stage_cfg=cfg[stage],
            changed_files=changed_files,
            working_dir=working_dir,
            action_templates=action_templates,
        )
        for action in stage_actions:
            pprint(f">> {stage} :: {action['name']}")
            pprint(f'command     : {action["run"]}')
            pprint(f'cwd         : {action["cwd"]}')
            pprint(f'return code : {action["returncode"]}')
            pprint(f'stdout      : {action["stdout"]}')
            pprint(f'stderr      : {action["stderr"]}')
        if not stage_success:
            sys.exit(1)


if __name__ == "__main__":
    optparser = ArgumentParser(description="A launch pad for cows")
    optparser.add_argument(
        "-c",
        "--config-file",
        default="moopad.yaml",
        metavar="moopad.yaml",
        help="Alternative configuration file, YAML format.",
    )
    optparser.add_argument(
        "-d",
        "--workdir",
        default=getcwd(),
        metavar="root/dir",
        help="Working directory. Actions will run in this directory by default.",
    )
    optparser.add_argument(
        "-f",
        "--changes-as-file",
        default=None,
        # dest='changes_as_files',
        metavar="changed.txt",
        help="Path to file containing list of changes, one file per line.",
    )
    optparser.add_argument(
        "-s",
        "--changes-as-string",
        default=None,
        # dest='changes_as_string',
        metavar="newline-separated-string",
        help="A string containing list of changed files, separated by newlines",
    )
    args = optparser.parse_args()

    config_file = args.config_file
    if args.changes_as_file is not None:
        with open(args.changes_as_file) as f:
            changed_files = [line.strip() for line in f if len(line) > 0]
    elif args.changes_as_string is not None:
        changed_files = [line.strip() for line in args.changes_as_string.splitlines()]
    else:
        changes = (
            "path1/changed_file1.py\n"
            "path2/sub2/file_changed_again.txt\n"
            "path3/sub1/sub2/sub4/changed\n"
            "path2/sub2\n"
        )
        changed_files = [line.strip() for line in changes.splitlines()]
    working_dir = str(Path(args.workdir).resolve())
    main(config_file=config_file, changed_files=changed_files, working_dir=working_dir)
