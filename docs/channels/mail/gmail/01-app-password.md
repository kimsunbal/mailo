# 01 — Gmail app passwords

> Source: <https://support.google.com/accounts/answer/185833> (read directly)
> Checked: 2026-08-13 · the original is authoritative

## 1. What it is

The original's definition: *"a **16-digit passcode** that gives a less secure app
or device permission to access your Google Account."*

It is not the account password. It is what a client that cannot do OAuth — such as
an SMTP client — authenticates with.

## 2. Requirements

**Two-factor authentication is mandatory.** The original: *"To create an app
password, you need 2-Step Verification on your Google Account."*

Where: Google Account → Security → 2-Step Verification → App passwords
(<https://myaccount.google.com/apppasswords>)

## 3. When it **cannot** be created — this drives the design

Three cases stated in the original:

1. **Two-factor is set up with security keys only**
2. **Signed in with a work, school, or other organisation account**
3. **Advanced Protection is enabled on the account**

Case 2 matters most. **Plenty of developers use a Google Workspace account as their
primary account.** Those users have no way to create an app password at all.

> An administrator can sometimes open the policy for an organisation account. But
> that does not change the important part: **the user cannot solve it themselves** —
> they have to go and ask.

## 4. Additional policy

- Google does not recommend them: *"App passwords aren't recommended and are
  unnecessary in most cases."* It points to "Sign in with Google" (OAuth) instead.
- **Changing the account password automatically revokes app passwords.**
  → The moment a user changes their password, mailo's mail delivery dies quietly.
    It surfaces as `SMTPAuthenticationError`, and the log message has to name this
    cause.
- The 16 digits shown at creation time are **shown only once.**

## 5. What this means for mailo

### 5.1 The SMTP channel is optional (settled)

Because of section 3, **onboarding that requires an app password is closed off to
some users by construction.**

```
mailo init
  -> "Paste your Discord webhook URL"   <- the default path
  -> "Set up mail as well? [y/N]"       <- defaults to no
```

The most valuable notification, `blocked`, goes over Discord, so the product works
completely without mail. Put mail at the first gate and people drop off there — and
the users in section 3 cannot get through at all.

### 5.2 OAuth is not in v1

Google recommends OAuth, but it does not fit mailo:

- The client secret would have to ship in the distribution, and in a public CLI a
  secret is not a secret
- It needs a browser redirect flow — worst possible fit for a headless GPU box or a
  container
- Token refresh brings state management, which undermines the "no daemon" principle

**Users for whom app passwords do not work are pointed at Discord instead.** That is
half the reason there are two channels — someone locked out of SMTP by construction
still needs a way to use this.

### 5.3 The error message has to name the cause

Printing "authentication failed" on `SMTPAuthenticationError` leaves the user
unable to fix it. The possible causes are few and specific, so say them:

```
SMTP authentication failed (smtp.gmail.com)
  Possible causes:
   - you changed your account password, which revokes app passwords -> create a new one
   - you entered the account password instead of an app password
   - this is an organisation or Advanced Protection account, which cannot use app passwords
     -> use Discord instead of the SMTP channel
  Create one at: https://myaccount.google.com/apppasswords
```
