# LoggerHead

A Discord bot that logs various events and activities in your Discord server.

## Features

- Logs a wide range of events, including:
  - Channel creation, deletion, and updates
  - Role creation, deletion, and updates
  - Server updates
  - Invite creation and deletion
  - Member join, leave, ban, kick, timeout, and updates
  - Message deletion and editing
  - Reaction addition and removal
  - Voice channel activity
  - Webhook updates
- Configurable logging channel and events to log for each server
- Batching of log messages for busy servers to avoid hitting rate limits
- Dynamic batching threshold based on server activity
- Periodic reporting of requests per second to monitor bot activity
- Supports multiple Discord servers, with the configuration for each server being stored in a PostgreSQL database

## Planned

- Caching of Discord messages to PostgresSQL database
  - This means if the bot is restarted then it still has a recollection of a certain number of chat messages per guild (Discord server)
- Refactoring
  - Yeah, I know, the code is probably not that tidy at the moment

## Installation

1. Clone the repository:

`git clone https://github.com/Ixe1/loggerhead.git`

2. Install the required dependencies:

`pip install -r requirements.txt`

3. Set up the configuration:
   - Create a `config.yaml` file in the project directory with the following structure:

```yaml
discord_token: "YOUR_DISCORD_BOT_TOKEN"
db_host: "YOUR_DATABASE_HOST"
db_user: "YOUR_DATABASE_USER"
db_password: "YOUR_DATABASE_PASSWORD"
db_name: "YOUR_DATABASE_NAME"
```

   - Replace the placeholders with your actual Discord bot token and database connection details.

4. Run the bot:

`python main.py`

## Usage

1. Invite the bot to your Discord server using the bot invite link.

2. Set the logging configuration using the following commands:
   - `!setlogconfig <log_channel> <log_events>`: Set the logging channel and events to log (comma-separated)
   - `!getlogconfig`: Get the current logging configuration
   - `!loghelp`: Display the list of available commands and configurable events

   Example: `!setlogconfig #log-channel member_join,member_leave,message_delete`

3. The bot will start logging the configured events in the designated logging channel.

4. By default, all events are enabled for logging. You can customize the events to log using the `!setlogconfig` command.

## Configurable Events

The following events can be configured for logging:

- `guild_channel_create`: Channel creation
- `guild_channel_delete`: Channel deletion
- `guild_channel_update`: Channel updates
- `guild_emojis_update`: Emoji updates
- `guild_role_create`: Role creation
- `guild_role_delete`: Role deletion
- `guild_role_update`: Role updates
- `guild_update`: Server updates
- `invite_create`: Invite creation
- `invite_delete`: Invite deletion
- `member_join`: Member join
- `member_remove`: Member leave
- `message_delete`: Message deletion
- `message_edit`: Message editing
- `member_ban`: Member ban
- `member_kick`: Member kick
- `member_remove_timeout`: Member timeout removal
- `member_timeout`: Member timeout
- `member_unban`: Member unban
- `member_update`: Member updates
- `reaction_add`: Reaction addition
- `reaction_remove`: Reaction removal
- `voice_state_update`: Voice channel activity
- `webhooks_update`: Webhook updates

## Database Configuration

The bot uses a PostgreSQL database to store the logging configuration for each server. Make sure to set up the database and provide the necessary connection details in the `config.yaml` file.

The bot will automatically create the required tables if they don't exist.

## Permissions

The bot requires the following permissions:

- View Channels
- Send Messages
- Embed Links
- Read Message History
- View Audit Log
- Manage Server (for invite tracking)
- Manage Webhooks

Make sure to grant the bot these permissions when inviting it to your server.

## Logging

The bot uses the `logging` module to log important information and errors. The log messages are displayed in the console.

## Rate Limiting

The bot handles rate limiting when sending log messages to avoid exceeding Discord's rate limits. It uses the `RateLimitedWebhook` class to handle rate limiting and retrying failed requests.

## Contributing

Contributions to the project are welcome! If you find any bugs, have feature requests, or want to contribute improvements, please submit an issue or a pull request on the GitHub repository.

To set up the development environment:
1. Clone the repository
2. Install the required dependencies
3. Set up the `config.yaml` file with your bot token and database connection details
4. Run the bot using `python main.py`

## Troubleshooting

- If the bot fails to connect to the database, make sure the database connection details in the `config.yaml` file are correct and the database is running.
- If the bot encounters any errors or issues, check the console output for error messages and refer to the logs for more details.
- If you encounter any other problems or have questions, please submit an issue on the GitHub repository.

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).