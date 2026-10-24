# ARTEMIS Termux Bridge

An isolated helper that lets ChatGPT send diagnostic commands to the ARTEMIS runtime inside Termux/Ubuntu through a private GitHub issue queue. It does not modify the clinic website Worker.

## Install

Run this once inside the existing Ubuntu terminal where ARTEMIS was installed:

    curl -fsSL https://raw.githubusercontent.com/clinicasaopauloparnamirim-coder/artemis-termux-bridge/main/install.sh | bash

The first run requires GitHub device authorization. When the terminal displays a code, open https://github.com/login/device in Chrome, enter the code, and approve. The client then posts a status message to the private queue and polls for new commands every four seconds.

Keep the Termux session running while ChatGPT sends commands.

## Safety and scope

- Source code is public; the command queue is private: clinicasaopauloparnamirim-coder/artemis-termux-bridge-queue, issue #1.
- Only commands posted by the connected account with the explicit command marker are executed.
- Commands run inside the existing Ubuntu/PRoot environment. This does not grant Android root access and does not expose a listening port.
- The GitHub credential stays in GitHub CLI on the phone. Do not send passwords, API keys, environment secrets, browser profiles, or private keys through the bridge.
- Stop the client with Ctrl+C or send the reserved stop command.
