# RoleMentionBot

This telegram bot adds a feature to groups and super-groups similar to mention a role in Discord.
Members can join some roles and get notified when the role mentioned.

## Variables

| Name         | Description                                 | Default |
|:------------:|:--------------------------------------------|:-------:|
| `PREFIX`     | Command Prefix                              | `;`     |
| `BATCH`      | Maximum number of mention in single message | `7`     |
| `MAX_ROLE`   | Maximum number of roles a user can have     | `10`    |
| `TOKEN`      | Bot token                                   | N/A     |
| `REGISTERED` | Registered groups id, separated by `:`      | N/A     |

You may set variables in `.env` file.

## Docker
If you know docker, you know...