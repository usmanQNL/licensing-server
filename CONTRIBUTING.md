# Contributing

Thanks for helping improve licensing-server. This project is licensed under the [Apache License 2.0](LICENSE), and contributions are accepted under the [Developer Certificate of Origin (DCO)](DCO).

## Sign off your commits

The DCO is a short statement that you wrote the change, or otherwise have the right to submit it under the project's license. You agree to it by adding a `Signed-off-by` line to every commit message:

```
Signed-off-by: Your Name <you@example.com>
```

Git adds the line for you when you commit with `-s`:

```bash
git commit -s -m "Fix grace period check in the Node verifier"
```

The name and email must match your Git identity (`git config user.name` and `git config user.email`). Anonymous or pseudonymous sign-offs are not accepted.

### Forgot to sign off?

Amend the last commit:

```bash
git commit --amend -s --no-edit
git push --force-with-lease
```

Or sign off every commit on your branch (replace `master` with the branch you started from):

```bash
git rebase --signoff master
git push --force-with-lease
```

## License of contributions

By contributing, you agree that your contribution is licensed under the Apache License 2.0, as described in section 5 of the [LICENSE](LICENSE). You keep the copyright to your own work.

## Before you open a pull request

- Run the tests (see the Test section of the README): `pytest -q`, plus the Node and Rust tests if you touched those verifiers.
- Never commit private keys, `.env` files, or deployment-specific files such as `keys.json`, `keylist.json` or `root-public.pem`. They are gitignored on purpose.
- Keep each pull request focused on one change and explain why it is needed.
