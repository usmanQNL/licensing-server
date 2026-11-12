# Contributing

Thanks for helping improve <APP NAME>. This project is licensed under the [<LICENSE NAME>](LICENSE), and contributions are accepted under the [Developer Certificate of Origin (DCO)](DCO).

## Sign off your commits

The DCO is a short statement that you wrote the change, or otherwise have the right to submit it under the project's license. You agree to it by adding a `Signed-off-by` line to every commit message:

```
Signed-off-by: Your Name <you@example.com>
```

Git adds the line for you when you commit with `-s`:

```bash
git commit -s -m "Describe your change"
```

The name and email must match your Git identity (`git config user.name` and `git config user.email`).

### Forgot to sign off?

Amend the last commit:

```bash
git commit --amend -s --no-edit
git push --force-with-lease
```

Or sign off every commit on your branch (replace `main` with the branch you started from):

```bash
git rebase --signoff main
git push --force-with-lease
```

## License of contributions

By contributing, you agree that your contribution is licensed under the same license as the project, the [<LICENSE NAME>](LICENSE). You keep the copyright to your own work.
