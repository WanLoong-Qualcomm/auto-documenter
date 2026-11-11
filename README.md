## Auto-documenter

Tracks screen activity and saves screenshots while activity is detected.

Screenshots are saved under `screenshots/<session-id>` in the application
directory by default. Set a different base directory with:

```console
uv run main.py --screenshot-base-directory ./captures
```

Each application session creates its own directory using the screenshot engine
object's ID.
