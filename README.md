# gh-local-fetcher

A simple tool to fetch a GitHub repository environments locally.

## How it works

### Pre-requisites:
1. Ngrok token in environment variable `NGROK_AUTHTOKEN`: Obtain a **free** [token](https://ngrok.com/docs/getting-started/). If already have the CLI installed get it by running `$ngrok config check`.
2. Github [API PAT token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)

### Install 

**With virtualenv:**

```
python3 -m venv myenv
source myenv/bin/activate
pip install -r requirements.txt
```

## Example

Fetch the value of `${{ secrets.TOKEN }}` and `${{ secrets.NAME }}` from the `staging` environment of the repository in path `/my/repo/dir`. 

```bash
$ gh-local-fetcher fetch --env staging --val secrets.TOKEN --val secrets.NAME -p /my/repo/dir

{
  "secrets.TOKEN": "some-token",
  "vars.NAME": "my-secret-name"
}
```
