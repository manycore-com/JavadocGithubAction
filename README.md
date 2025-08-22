# JavadocGithubAction
Github Action to automatically add Javadoc comments

## What is it
When you create a PR, and when you do a new push to a PR, this action will run on all Java files. It will add Javadoc comments to non trivial classes, and methods.

You can tweak its behavior in scripts/github_action_javadoc/CUSTOMER-PROMPT.md. 

## How to test it locally
You need the dependencies in scripts/github_action_javadoc/requirements.txt

Feel free to create an environment in for example miniconda for it
```bash
conda create -n javadoc python=3.12
conda activate javadoc
pip install -r scripts/github_action_javadoc/requirements.txt
```

In scripts/github_action_javadoc/ you have action.py that is used by the Github Action. You also have standalone.py which you can use from the terminal:

```bash
python3 scripts/github_action_javadoc/standalone.py path/to/javafile.java
```

## Installation

1. on your repository, go to settings. Click "Secrets and variables" on the left side, and then Actions. Under "Repository settings", click "New repository secret" and add ANTHROPIC_API_KEY (you can create one on https://console.anthropic.com/settings/keys).
2. To ensure the github Action can run, go to repositort settings, click "Actions" to the left, then "General", and "Allow all actions and reusable workflows" is enabled.
3. copy .github/workflows/github_action_javadoc.yml to your java project.
4. copy scripts/ to your java project.
