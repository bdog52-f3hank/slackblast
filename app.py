import email
import logging
import json
import os
import datetime
from datetime import datetime, timezone, timedelta
import re
import pandas as pd

from slack_bolt import App
from slack_bolt.adapter.aws_lambda import SlackRequestHandler
from slack_bolt.adapter.aws_lambda.lambda_s3_oauth_flow import LambdaS3OAuthFlow

import mysql.connector
from contextlib import ContextDecorator

from cryptography.fernet import Fernet

import sendmail

# def email_test2():
#     sendmail.send(subject='testing', recipient='evan.petzoldt@protonmail.com', body='this is a test', email_server='smtp.gmail.com', email_server_port=587, email_user='f3.qsignups@gmail.com', email_password='fqeunnunlfefrinw')

# email_test2()

# def get_categories():
#     with open('categories.json') as c:
#         data = json.load(c)
#         return data


# def formatted_categories(filteredcats):
#     opts = []
#     for cat in filteredcats:
#         x = {
#             "text": {
#                 "type": "plain_text",
#                 "text": cat["name"]
#             },
#             "value": str(cat["id"])
#         }
#         opts.append(x)
#     return opts

OPTIONAL_INPUT_VALUE = "None"

logger = logging.getLogger()
logger.setLevel(logging.INFO)
# logging.basicConfig(level=logging.DEBUG)
#categories = []

# process_before_response must be True when running on FaaS
slack_app = App(
    process_before_response=True,
    oauth_flow=LambdaS3OAuthFlow(),
)

#categories = get_categories()

# Construct class for connecting to the db
# Takes team_id as an input, pulls schema name from paxminer.regions
class my_connect(ContextDecorator):
    def __init__(self):
        self.conn = ''

    def __enter__(self):
        self.conn = mysql.connector.connect(
            host=os.environ['DATABASE_HOST'],
            user=os.environ['ADMIN_DATABASE_USER'],
            passwd=os.environ['ADMIN_DATABASE_PASSWORD'],
            database=os.environ['ADMIN_DATABASE_SCHEMA']
        )
        return self

    def __exit__(self, *exc):
        self.conn.close()
        return False


class my_connect(ContextDecorator):
    def __init__(self):
        self.conn = ''

    def __enter__(self):
        self.conn = mysql.connector.connect(
            host="f3stlouis.cac36jsyb5ss.us-east-2.rds.amazonaws.com",
            user="moneyball",
            passwd="AyeF3smartypants!",
            database="slackblast"
        )
        return self

    def __exit__(self, *exc):
        self.conn.close()
        return False


@slack_app.middleware  # or app.use(log_request)
def log_request(logger, body, next):
    logger.debug(body)
    return next()


@slack_app.event("app_mention")
def event_test(body, say, logger):
    logger.info(body)
    say("What's up yo?")


@slack_app.event("message")
def handle_message():
    pass


def safeget(dct, *keys):
    for key in keys:
        try:
            dct = dct[key]
        except KeyError:
            return None
    return dct


def get_channel_id_and_name(body, logger):
    # returns channel_iid, channel_name if it exists as an escaped parameter of slashcommand
    user_id = body.get("user_id")
    # Get "text" value which is everything after the /slash-command
    # e.g. /slackblast #our-aggregate-backblast-channel
    # then text would be "#our-aggregate-backblast-channel" if /slash command is not encoding
    # but encoding needs to be checked so it will be "<#C01V75UFE56|our-aggregate-backblast-channel>" instead
    channel_name = body.get("text") or ''
    channel_id = ''
    try:
        channel_id = channel_name.split('|')[0].split('#')[1]
        channel_name = channel_name.split('|')[1].split('>')[0]
    except IndexError as ierr:
        logger.error('Bad user input - cannot parse channel id')
    except Exception as error:
        logger.error('User did not pass in any input')
    return channel_id, channel_name


def get_channel_name(id, logger, client):
    channel_info_dict = client.conversations_info(
        channel=id
    )
    channel_name = safeget(channel_info_dict, 'channel', 'name') or None
    logger.info('channel_name is {}'.format(channel_name))
    return channel_name


def get_user_names(array_of_user_ids, logger, client, return_urls = False):
    names = []
    urls = []
    for user_id in array_of_user_ids:
        user_info_dict = client.users_info(
            user=user_id
        )
        user_name = safeget(user_info_dict, 'user', 'profile', 'display_name') or safeget(
            user_info_dict, 'user', 'profile', 'real_name') or None
        if user_name:
            names.append(user_name)
        logger.info('user_name is {}'.format(user_name))

        user_icon_url = user_info_dict['user']['profile']['image_192']
        urls.append(user_icon_url)
    logger.info('names are {}'.format(names))

    if return_urls:
        return names, urls
    else:
        return names

def get_user_ids(user_names, client):
    member_list = pd.DataFrame(client.users_list()['members'])
    member_list = member_list.drop('profile', axis=1).join(pd.DataFrame(member_list.profile.values.tolist()), rsuffix='_profile')
    member_list['display_name2'] = member_list['display_name']
    member_list.loc[(member_list['display_name']==''), ('display_name2')] = member_list['real_name']
    member_list['display_name2'] = member_list['display_name2'].str.lower()
    member_list['display_name2'].replace('\s\(([\s\S]*?\))','',regex=True, inplace=True)
    
    user_ids = []
    for user_name in user_names:
        user_name = user_name.replace('_', ' ').lower()
        try:
            user = f"<@{member_list.loc[(member_list['display_name2']==user_name), ('id')].iloc[0]}>"
            print(f'Found {user_name}: {user}')
        except:
            user = user_name
        user_ids.append(user)
    
    return user_ids

def parse_moleskin_users(msg, client):
    pattern = "@([A-Za-z0-9-']+)"
    user_ids = get_user_ids(re.findall(pattern, msg), client)

    msg2 = re.sub(pattern, '{}', msg).format(*user_ids)
    return msg2

def respond_to_slack_within_3_seconds(body, ack):
    ack("Opening form...")

def command(ack, body, respond, client, logger, context):
    today = datetime.now(timezone.utc).astimezone()
    today = today - timedelta(hours=6)
    datestring = today.strftime("%Y-%m-%d")
    user_id = body.get("user_id")

    team_id = context['team_id']
    bot_token = context['bot_token']

    # Figure out where user sent slashcommand from to set current channel id and name
    is_direct_message = body.get("channel_name") == 'directmessage'
    current_channel_id = user_id if is_direct_message else body.get(
        "channel_id")
    current_channel_name = "Me" if is_direct_message else body.get(
        "channel_id")

    # The channel where user submitted the slashcommand
    current_channel_option = {
        "text": {
            "type": "plain_text",
            "text": "Current Channel"
        },
        "value": current_channel_id
    }

    # In .env, CHANNEL=USER
    channel_me_option = {
        "text": {
            "type": "plain_text",
            "text": "Me"
        },
        "value": user_id
    }
    # In .env, CHANNEL=THE_AO
    channel_the_ao_option = {
        "text": {
            "type": "plain_text",
            "text": "The AO Channel"
        },
        "value": "THE_AO"
    }
    # In .env, CHANNEL=<channel-id>
    channel_configured_ao_option = {
        "text": {
            "type": "plain_text",
            "text": "Preconfigured Backblast Channel"
        },
        # "value": config('CHANNEL', default=current_channel_id)
        "value": current_channel_id
    }
    # User may have typed /slackblast #<channel-name> AND
    # slackblast slashcommand is checked to escape channels.
    #   Escape channels, users, and links sent to your app
    #   Escaped: <#C1234|general>
    channel_id, channel_name = get_channel_id_and_name(body, logger)
    channel_user_specified_channel_option = {
        "text": {
            "type": "plain_text",
            "text": '# ' + channel_name
        },
        "value": channel_id
    }

    channel_options = []

    # figure out which channel should be default/initial and then remaining operations
    # now going with a default of the AO channel
    # if channel_id:
    #     initial_channel_option = channel_user_specified_channel_option
    #     channel_options.append(channel_user_specified_channel_option)
    #     channel_options.append(current_channel_option)
    #     channel_options.append(channel_me_option)
    #     channel_options.append(channel_the_ao_option)
    #     channel_options.append(channel_configured_ao_option)
    # # elif config('CHANNEL', default=current_channel_id) == 'USER':
    # elif current_channel_id == 'USER':
    #     initial_channel_option = channel_me_option
    #     channel_options.append(channel_me_option)
    #     channel_options.append(current_channel_option)
    #     channel_options.append(channel_the_ao_option)
    # # elif config('CHANNEL', default=current_channel_id) == 'THE_AO':
    # elif current_channel_id == 'THE_AO':
    initial_channel_option = channel_the_ao_option
    channel_options.append(channel_the_ao_option)
    channel_options.append(current_channel_option)
    channel_options.append(channel_me_option)
    # # elif config('CHANNEL', default=current_channel_id) == current_channel_id:
    # elif current_channel_id == current_channel_id:
    #     # if there is no .env CHANNEL value, use default of current channel
    #     initial_channel_option = current_channel_option
    #     channel_options.append(current_channel_option)
    #     channel_options.append(channel_me_option)
    #     channel_options.append(channel_the_ao_option)
    # else:
    #     # Default to using the .env CHANNEL value which at this point must be a channel id
    #     initial_channel_option = channel_configured_ao_option
    #     channel_options.append(channel_configured_ao_option)
    #     channel_options.append(current_channel_option)
    #     channel_options.append(channel_me_option)
    #     channel_options.append(channel_the_ao_option)

    # determine if backblast or preblast
    is_preblast = body.get("command") == '/preblast'

    if is_preblast:
        blocks = [
            {
                "type": "input",
                "block_id": "title",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "title",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Snarky Title?"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Title"
                }
            },
            {
                "type": "input",
                "block_id": "the_ao",
                "element": {
                    "type": "channels_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select the AO",
                        "emoji": True
                    },
                    "action_id": "channels_select-action"
                },
                "label": {
                    "type": "plain_text",
                    "text": "The AO",
                    "emoji": True
                }
            },
            {
                "type": "input",
                "block_id": "date",
                "element": {
                    "type": "datepicker",
                    "initial_date": datestring,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select a date",
                        "emoji": True
                    },
                    "action_id": "datepicker-action"
                },
                "label": {
                    "type": "plain_text",
                    "text": "Workout Date",
                    "emoji": True
                }
            },
            {
                "type": "input",
                "block_id": "time",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "time-action",
                    "initial_value": "0530",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Workout time"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Workout Time"
                }
            },
            {
                "type": "input",
                "block_id": "the_q",
                "element": {
                    "type": "users_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Tag the Q",
                        "emoji": True
                    },
                    "action_id": "users_select-action"
                },
                "label": {
                    "type": "plain_text",
                    "text": "The Q",
                    "emoji": True
                }
            },
            # {
            #     "type": "input",
            #     "block_id": "the_coq",
            #     "element": {
            #         "type": "users_select",
            #         "placeholder": {
            #             "type": "plain_text",
            #             "text": "Tag the CoQ(s)",
            #             "emoji": True
            #         },
            #         "action_id": "multi_users_select-action"
            #     },
            #     "label": {
            #         "type": "plain_text",
            #         "text": "The CoQs, if applicable",
            #         "emoji": True
            #     },
            #     "optional": True
            # },
            {
                "type": "input",
                "block_id": "why",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "why-action",
                    "initial_value": "None",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Explain the why"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "The Why"
                }
            },
            {
                "type": "input",
                "block_id": "coupon",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "coupon-action",
                    "initial_value": "None",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Coupons or not?"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Coupons"
                }
            },
            {
                "type": "input",
                "block_id": "fngs",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "fng-action",
                    "initial_value": "None",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Any message for FNGs?"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "FNGs"
                }
            },
            {
                "type": "input",
                "block_id": "moleskine",
                "element": {
                    "type": "plain_text_input",
                    "multiline": True,
                    "action_id": "plain_text_input-action",
                    "initial_value": "None",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Any additional beatdown detail, announcements, etc.\n\n"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "The Moleskine",
                    "emoji": True
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "input",
                "block_id": "destination",
                "element": {
                    "type": "static_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select an item",
                        "emoji": True
                    },
                    "options": channel_options,
                    "initial_option": initial_channel_option,
                    "action_id": "destination-input"
                },
                "label": {
                    "type": "plain_text",
                    "text": "Choose where to post this",
                    "emoji": True
                }
            },
            {
            "type": "context",
                "elements": [
                    {
                        "type": "plain_text",
                        "text": "Please wait after hitting Submit!",
                        "emoji": True
                    }
                ]
            }
        ]
        view = {
            "type": "modal",
            "callback_id": "preblast-id",
            "title": {
                "type": "plain_text",
                "text": "Create a Preblast"
            },
            "submit": {
                "type": "plain_text",
                "text": "Submit"
            },
            "blocks": blocks
        }
    else:
        blocks = [
            {
                "type": "input",
                "block_id": "title",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "title",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Snarky Title?"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Title"
                }
            },
            {
                "type": "input",
                "block_id": "the_ao",
                "element": {
                    "type": "channels_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select the AO",
                        "emoji": True
                    },
                    "action_id": "channels_select-action"
                },
                "label": {
                    "type": "plain_text",
                    "text": "The AO",
                    "emoji": True
                }
            },
            {
                "type": "input",
                "block_id": "date",
                "element": {
                    "type": "datepicker",
                    "initial_date": datestring,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select a date",
                        "emoji": True
                    },
                    "action_id": "datepicker-action"
                },
                "label": {
                    "type": "plain_text",
                    "text": "Workout Date",
                    "emoji": True
                }
            },
            {
                "type": "input",
                "block_id": "the_q",
                "element": {
                    "type": "users_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Tag the Q",
                        "emoji": True
                    },
                    "action_id": "users_select-action"
                },
                "label": {
                    "type": "plain_text",
                    "text": "The Q",
                    "emoji": True
                }
            },
            {
                "type": "input",
                "block_id": "the_coq",
                "element": {
                    "type": "multi_users_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Tag the CoQ(s)",
                        "emoji": True
                    },
                    "action_id": "multi_users_select-action"
                },
                "label": {
                    "type": "plain_text",
                    "text": "The CoQ(s), if applicable",
                    "emoji": True
                },
                "optional": True
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "plain_text",
                        "text": "Note, only the first CoQ is tracked by PAXMiner",
                        "emoji": True
                    }
                ]
            },
            {
                "type": "input",
                "block_id": "the_pax",
                "element": {
                    "type": "multi_users_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Tag the PAX",
                        "emoji": True
                    },
                    "action_id": "multi_users_select-action"
                },
                "label": {
                    "type": "plain_text",
                    "text": "The PAX",
                    "emoji": True
                }
            },
            {
                "type": "input",
                "block_id": "non_slack_pax",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "non_slack_pax-action",
                    "initial_value": "None",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Non-Slackers"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "List untaggable PAX separated by commas (not including FNGs)"
                }
            },
            {
                "type": "input",
                "block_id": "fngs",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "fng-action",
                    "initial_value": "None",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "FNGs"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "List FNGs separated by commas"
                }
            },
            {
                "type": "input",
                "block_id": "count",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "count-action",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Total PAX count including FNGs"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Count"
                }
            },
            {
                "type": "input",
                "block_id": "moleskine",
                "element": {
                    "type": "plain_text_input",
                    "multiline": True,
                    "action_id": "plain_text_input-action",
                    "initial_value": "\n*WARMUP:* \n*THE THANG:* \n*MARY:* \n*ANNOUNCEMENTS:* \n*COT:* ",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Tell us what happened\n\n"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "The Moleskine",
                    "emoji": True
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "plain_text",
                        "text": "If trying to tag PAX in here, substitute _ for spaces and do not include titles in parenthesis (ie, @Moneyball not @Moneyball_(F3_STC)). Spelling is important, capitalization is not!",
                        "emoji": True
                    }
                ]
            },
            {
                "type": "divider"
            },
            # {
            #     "type": "section",
            #     "block_id": "destination",
            #     "text": {
            #         "type": "plain_text",
            #         "text": "Choose where to post this"
            #     },
            #     "accessory": {
            #         "action_id": "destination-action",
            #         "type": "static_select",
            #         "placeholder": {
            #             "type": "plain_text",
            #             "text": "Choose where"
            #         },
            #         "initial_option": initial_channel_option,
            #         "options": channel_options
            #     }
            # },
            {
                "type": "input",
                "block_id": "destination",
                "element": {
                    "type": "static_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select an item",
                        "emoji": True
                    },
                    "options": channel_options,
                    "initial_option": initial_channel_option,
                    "action_id": "destination-input"
                },
                "label": {
                    "type": "plain_text",
                    "text": "Choose where to post this",
                    "emoji": True
                }
            }
        ]

        # Check to see if email is enabled for the region
        try:
            with my_connect() as mydb:
                mycursor = mydb.conn.cursor()
                mycursor.execute(f'SELECT email_enabled, email_option_show FROM regions WHERE team_id = "{team_id}";')
                email_enabled, email_option_show = mycursor.fetchone()
                print(f'email_enabled: {email_enabled}')
        except Exception as e:
            logging.error(f"Error pulling user db email info: {e}")
    
        try:
            if (email_enabled == 1) & (email_option_show == 1):
                blocks.append({
                    "type": "input",
                    "block_id": "email_send",
                    "element": {
                        "type": "radio_buttons",
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Send email",
                                    "emoji": True
                                },
                                "value": "yes"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Don't send email",
                                    "emoji": True
                                },
                                "value": "no"
                            },                    
                        ],
                        "action_id": "email_send",
                        "initial_option": {
                            "text": {
                                "type": "plain_text",
                                "text": "Send email",
                                "emoji": True
                            },
                            "value": "yes"
                        }
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Email Backblast (to Wordpress, etc.)",
                        "emoji": True
                    }
                })
        except Exception as e:
            logging.error(f"{e}")

        blocks.append({
            "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "*Do not hit Submit more than once!* Even if you get a timeout error, the backblast has likely already been posted. If using email, this can take time and this form may not automatically close."
                    }
                ]
        })

        view = {
            "type": "modal",
            "callback_id": "backblast-id",
            "title": {
                "type": "plain_text",
                "text": "Create a Backblast"
            },
            "submit": {
                "type": "plain_text",
                "text": "Submit"
            },
            "blocks": blocks
        }

    res = client.views_open(
        trigger_id=body["trigger_id"],
        view=view,
    )
    logger.info(res)

def command_labs(ack, body, respond, client, logger, context):
    today = datetime.now(timezone.utc).astimezone()
    today = today - timedelta(hours=6)
    datestring = today.strftime("%Y-%m-%d")
    user_id = body.get("user_id")

    team_id = context['team_id']
    bot_token = context['bot_token']

    # Figure out where user sent slashcommand from to set current channel id and name
    is_direct_message = body.get("channel_name") == 'directmessage'
    current_channel_id = user_id if is_direct_message else body.get(
        "channel_id")
    current_channel_name = "Me" if is_direct_message else body.get(
        "channel_id")

    # The channel where user submitted the slashcommand
    current_channel_option = {
        "text": {
            "type": "plain_text",
            "text": "Current Channel"
        },
        "value": current_channel_id
    }

    # In .env, CHANNEL=USER
    channel_me_option = {
        "text": {
            "type": "plain_text",
            "text": "Me"
        },
        "value": user_id
    }
    # In .env, CHANNEL=THE_AO
    channel_the_ao_option = {
        "text": {
            "type": "plain_text",
            "text": "The AO Channel"
        },
        "value": "THE_AO"
    }
    # In .env, CHANNEL=<channel-id>
    channel_configured_ao_option = {
        "text": {
            "type": "plain_text",
            "text": "Preconfigured Backblast Channel"
        },
        # "value": config('CHANNEL', default=current_channel_id)
        "value": current_channel_id
    }
    # User may have typed /slackblast #<channel-name> AND
    # slackblast slashcommand is checked to escape channels.
    #   Escape channels, users, and links sent to your app
    #   Escaped: <#C1234|general>
    channel_id, channel_name = get_channel_id_and_name(body, logger)
    channel_user_specified_channel_option = {
        "text": {
            "type": "plain_text",
            "text": '# ' + channel_name
        },
        "value": channel_id
    }

    channel_options = []

    # figure out which channel should be default/initial and then remaining operations
    # now going with a default of the AO channel
    # if channel_id:
    #     initial_channel_option = channel_user_specified_channel_option
    #     channel_options.append(channel_user_specified_channel_option)
    #     channel_options.append(current_channel_option)
    #     channel_options.append(channel_me_option)
    #     channel_options.append(channel_the_ao_option)
    #     channel_options.append(channel_configured_ao_option)
    # # elif config('CHANNEL', default=current_channel_id) == 'USER':
    # elif current_channel_id == 'USER':
    #     initial_channel_option = channel_me_option
    #     channel_options.append(channel_me_option)
    #     channel_options.append(current_channel_option)
    #     channel_options.append(channel_the_ao_option)
    # # elif config('CHANNEL', default=current_channel_id) == 'THE_AO':
    # elif current_channel_id == 'THE_AO':
    initial_channel_option = channel_the_ao_option
    channel_options.append(channel_the_ao_option)
    channel_options.append(current_channel_option)
    channel_options.append(channel_me_option)
    # # elif config('CHANNEL', default=current_channel_id) == current_channel_id:
    # elif current_channel_id == current_channel_id:
    #     # if there is no .env CHANNEL value, use default of current channel
    #     initial_channel_option = current_channel_option
    #     channel_options.append(current_channel_option)
    #     channel_options.append(channel_me_option)
    #     channel_options.append(channel_the_ao_option)
    # else:
    #     # Default to using the .env CHANNEL value which at this point must be a channel id
    #     initial_channel_option = channel_configured_ao_option
    #     channel_options.append(channel_configured_ao_option)
    #     channel_options.append(current_channel_option)
    #     channel_options.append(channel_me_option)
    #     channel_options.append(channel_the_ao_option)

    blocks = [
        {
            "type": "input",
            "block_id": "title",
            "element": {
                "type": "plain_text_input",
                "action_id": "title",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Snarky Title?"
                }
            },
            "label": {
                "type": "plain_text",
                "text": "Title"
            }
        },
        {
            "type": "input",
            "block_id": "the_ao",
            "element": {
                "type": "channels_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select the AO",
                    "emoji": True
                },
                "action_id": "channels_select-action"
            },
            "label": {
                "type": "plain_text",
                "text": "The AO",
                "emoji": True
            }
        },
        {
            "type": "input",
            "block_id": "date",
            "element": {
                "type": "datepicker",
                "initial_date": datestring,
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select a date",
                    "emoji": True
                },
                "action_id": "datepicker-action"
            },
            "label": {
                "type": "plain_text",
                "text": "Workout Date",
                "emoji": True
            }
        },
        {
            "type": "input",
            "block_id": "the_q",
            "element": {
                "type": "users_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Tag the Q",
                    "emoji": True
                },
                "action_id": "users_select-action"
            },
            "label": {
                "type": "plain_text",
                "text": "The Q",
                "emoji": True
            }
        },
        {
            "type": "input",
            "block_id": "the_coq",
            "element": {
                "type": "multi_users_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Tag the CoQ(s)",
                    "emoji": True
                },
                "action_id": "multi_users_select-action"
            },
            "label": {
                "type": "plain_text",
                "text": "The CoQ(s), if applicable",
                "emoji": True
            },
            "optional": True
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "plain_text",
                    "text": "Note, only the first CoQ is tracked by PAXMiner",
                    "emoji": True
                }
            ]
        },
        {
            "type": "input",
            "block_id": "the_pax",
            "element": {
                "type": "multi_users_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Tag the PAX",
                    "emoji": True
                },
                "action_id": "multi_users_select-action"
            },
            "label": {
                "type": "plain_text",
                "text": "The PAX",
                "emoji": True
            }
        },
        {
            "type": "input",
            "block_id": "non_slack_pax",
            "element": {
                "type": "plain_text_input",
                "action_id": "non_slack_pax-action",
                "initial_value": "None",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Non-Slackers"
                }
            },
            "label": {
                "type": "plain_text",
                "text": "List untaggable PAX separated by commas (not including FNGs)"
            }
        },
        {
            "type": "input",
            "block_id": "fngs",
            "element": {
                "type": "plain_text_input",
                "action_id": "fng-action",
                "initial_value": "None",
                "placeholder": {
                    "type": "plain_text",
                    "text": "FNGs"
                }
            },
            "label": {
                "type": "plain_text",
                "text": "List FNGs separated by commas"
            }
        },
        {
            "type": "input",
            "block_id": "count",
            "element": {
                "type": "plain_text_input",
                "action_id": "count-action",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Total PAX count including FNGs"
                }
            },
            "label": {
                "type": "plain_text",
                "text": "Count"
            }
        },
        {
            "type": "input",
            "block_id": "moleskine",
            "element": {
                "type": "plain_text_input",
                "multiline": True,
                "action_id": "plain_text_input-action",
                "initial_value": "\n*WARMUP:* \n*THE THANG:* \n*MARY:* \n*ANNOUNCEMENTS:* \n*COT:* ",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Tell us what happened\n\n"
                }
            },
            "label": {
                "type": "plain_text",
                "text": "The Moleskine",
                "emoji": True
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "plain_text",
                    "text": "If trying to tag PAX in here, substitute _ for spaces and do not include titles in parenthesis (ie, @Moneyball not @Moneyball_(F3_STC)). Spelling is important, capitalization is not!",
                    "emoji": True
                }
            ]
        },
        {
            "type": "divider"
        },
        # {
        #     "type": "section",
        #     "block_id": "destination",
        #     "text": {
        #         "type": "plain_text",
        #         "text": "Choose where to post this"
        #     },
        #     "accessory": {
        #         "action_id": "destination-action",
        #         "type": "static_select",
        #         "placeholder": {
        #             "type": "plain_text",
        #             "text": "Choose where"
        #         },
        #         "initial_option": initial_channel_option,
        #         "options": channel_options
        #     }
        # },
        {
            "type": "input",
            "block_id": "destination",
            "element": {
                "type": "static_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select an item",
                    "emoji": True
                },
                "options": channel_options,
                "initial_option": initial_channel_option,
                "action_id": "destination-input"
            },
            "label": {
                "type": "plain_text",
                "text": "Choose where to post this",
                "emoji": True
            }
        }
    ]

    # Check to see if email is enabled for the region
    try:
        with my_connect() as mydb:
            mycursor = mydb.conn.cursor()
            mycursor.execute(f'SELECT email_enabled, email_option_show FROM regions WHERE team_id = "{team_id}";')
            email_enabled, email_option_show = mycursor.fetchone()
            print(f'email_enabled: {email_enabled}')
    except Exception as e:
        logging.error(f"Error pulling user db email info: {e}")

    try:
        if (email_enabled == 1) & (email_option_show == 1):
            blocks.append({
                "type": "input",
                "block_id": "email_send",
                "element": {
                    "type": "radio_buttons",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Send email",
                                "emoji": True
                            },
                            "value": "yes"
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Don't send email",
                                "emoji": True
                            },
                            "value": "no"
                        },                    
                    ],
                    "action_id": "email_send",
                    "initial_option": {
                        "text": {
                            "type": "plain_text",
                            "text": "Send email",
                            "emoji": True
                        },
                        "value": "yes"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Email Backblast (to Wordpress, etc.)",
                    "emoji": True
                }
            })
    except Exception as e:
        logging.error(f"{e}")

    blocks.append({
        "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "*Do not hit Submit more than once!* Even if you get a timeout error, the backblast has likely already been posted. If using email, this can take time and this form may not automatically close."
                }
            ]
    })

    view = {
        "type": "modal",
        "callback_id": "backblast-id-labs",
        "title": {
            "type": "plain_text",
            "text": "Create a Backblast"
        },
        "submit": {
            "type": "plain_text",
            "text": "Submit"
        },
        "blocks": blocks
    }

    res = client.views_open(
        trigger_id=body["trigger_id"],
        view=view,
    )
    logger.info(res)
        
# def email_test(body, client, context):
#     sendmail.send(subject='testing', recipient='evan.petzoldt@protonmail.com', body='this is a test', email_server='smtp.gmail.com', email_server_port=587, email_user='f3.qsignups@gmail.com', email_password='p24RoaZzBW#Q!L')

def config_slackblast(body, client, context):
    team_id = context['team_id']
    bot_token = context['bot_token']

    # Pull current settings
    try:
        with my_connect() as mydb:
            region_df = pd.read_sql(f'SELECT * FROM regions WHERE team_id = "{team_id}";', mydb.conn)
    except Exception as e:
        logging.error(f"Error pulling user db email info: {e}")
    

    email_enable_options = [
        {
            "text": {
                "type": "plain_text",
                "text": "Enable email",
                "emoji": True
            },
            "value": "enable"
        },
        {
            "text": {
                "type": "plain_text",
                "text": "Disable email",
                "emoji": True
            },
            "value": "disable"
        },                    
    ]

    email_option_show_options = [
        {
            "text": {
                "type": "plain_text",
                "text": "Show",
                "emoji": True
            },
            "value": "yes"
        },
        {
            "text": {
                "type": "plain_text",
                "text": "Don't show",
                "emoji": True
            },
            "value": "no"
        },                    
    ]

    postie_format_options = [
        {
            "text": {
                "type": "plain_text",
                "text": "Yes",
                "emoji": True
            },
            "value": "yes"
        },
        {
            "text": {
                "type": "plain_text",
                "text": "No",
                "emoji": True
            },
            "value": "no"
        },                    
    ]

    # build out starting defaults
    try:
        region_info = region_df.loc[0,] # will fail if team not on the regions table
        if region_info['email_enabled'] == 1:
            email_enable_initial = email_enable_options[0]
        else:
            email_enable_initial = email_enable_options[1]

        if region_info['email_option_show'] == 1:
            email_option_show_initial = email_option_show_options[0]
        else:
            email_option_show_initial = email_option_show_options[1]

        if region_info['postie_format'] == 1:
            postie_format_initial = postie_format_options[0]
        else:
            postie_format_initial = postie_format_options[1]

        email_server_initial = region_info['email_server']
        email_port_initial = str(region_info['email_server_port'])
        email_user_initial = region_info['email_user']
        fernet = Fernet(os.environ['PASSWORD_ENCRYPT_KEY'].encode())
        email_password_initial = fernet.decrypt(region_info['email_password'].encode()).decode()
        email_to_initial = region_info['email_to']
    except Exception as e:
        # if the pull does not return anything
        print(f'Hit error: {e}')
        email_enable_initial = email_enable_options[1]
        email_option_show_initial = email_option_show_options[1]
        postie_format_initial = postie_format_options[1]
        email_server_initial = 'smtp.gmail.com'
        email_port_initial = '587'
        email_user_initial = 'example_sender@gmail.com'
        email_password_initial = 'example_pwd_123'
        email_to_initial = 'example_destination@gmail.com'

    blocks = [
		{
			"type": "input",
            "block_id": "email_enable",
			"element": {
				"type": "radio_buttons",
				"options": email_enable_options,
				"action_id": "email_enable",
                "initial_option": email_enable_initial
			},
			"label": {
				"type": "plain_text",
				"text": "Slackblast Email",
				"emoji": True
			}
		},
        {
			"type": "input",
            "block_id": "email_option_show",
			"element": {
				"type": "radio_buttons",
				"options": email_option_show_options,
				"action_id": "email_option_show",
                "initial_option": email_option_show_initial
			},
			"label": {
				"type": "plain_text",
				"text": "Show email option in form?",
				"emoji": True
			}
		},
        {
            "type": "input",
            "block_id": "email_server",
            "element": {
                "type": "plain_text_input",
                "action_id": "email_server",
                "initial_value": email_server_initial
            },
            "label": {
                "type": "plain_text",
                "text": "Email Server"
            }
        },
        {
            "type": "input",
            "block_id": "email_port",
            "element": {
                "type": "plain_text_input",
                "action_id": "email_port",
                "initial_value": email_port_initial
            },
            "label": {
                "type": "plain_text",
                "text": "Email Server Port"
            }
        },
        {
            "type": "input",
            "block_id": "email_user",
            "element": {
                "type": "plain_text_input",
                "action_id": "email_user",
                "initial_value": email_user_initial
            },
            "label": {
                "type": "plain_text",
                "text": "Email From Address"
            }
        },
        {
            "type": "input",
            "block_id": "email_password",
            "element": {
                "type": "plain_text_input",
                "action_id": "email_password",
                "initial_value": email_password_initial
            },
            "label": {
                "type": "plain_text",
                "text": "Email Password"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "If using gmail, you must use an App Password (https://support.google.com/accounts/answer/185833). Your password will be stored encrypted - however, it is STRONGLY recommended that you use a non-personal email address and password for this purpose, as security cannot be guaranteed.",
                }
            ]
        },
        {
            "type": "input",
            "block_id": "email_to",
            "element": {
                "type": "plain_text_input",
                "action_id": "email_to",
                "initial_value": email_to_initial
            },
            "label": {
                "type": "plain_text",
                "text": "Email To Address"
            }
        },
        {
			"type": "input",
            "block_id": "postie_format",
			"element": {
				"type": "radio_buttons",
				"options": postie_format_options,
				"action_id": "postie_format",
                "initial_option": postie_format_initial
			},
			"label": {
				"type": "plain_text",
				"text": "Use Postie formatting for categories, tags?",
				"emoji": True
			}
		},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "This will put the AO name as a category for the post, and will put PAX names at the end as tags.",
                }
            ]
        }
    ]
    view = {
        "type": "modal",
        "callback_id": "config-slackblast",
        "title": {
            "type": "plain_text",
            "text": "Configure settings"
        },
        "submit": {
            "type": "plain_text",
            "text": "Submit"
        },
        "blocks": blocks
    }

    res = client.views_open(
        trigger_id=body["trigger_id"],
        view=view,
    )
    logger.info(res)

@slack_app.view("config-slackblast")
def view_submission(ack, body, logger, client, context):
    ack()
    team_id = context['team_id']
    bot_token = context['bot_token']
    # logging.info(body)
    # logging.info(client.team_info())
    try:
        team_info = client.team_info()
        workspace_name = team_info['team']['name']
    except:
        workspace_name = ''

    # gather inputs
    result = body["view"]["state"]["values"]
    email_enable = result['email_enable']['email_enable']['selected_option']['value'] == "enable"
    email_option_show = result['email_option_show']['email_option_show']['selected_option']['value'] == "yes"
    email_server = result['email_server']['email_server']['value']
    email_port = result['email_port']['email_port']['value']
    email_user = result['email_user']['email_user']['value']
    email_password_raw = result['email_password']['email_password']['value']
    email_to = result['email_to']['email_to']['value']
    postie_format = result['postie_format']['postie_format']['selected_option']['value'] == "yes"

    # encrypt password
    fernet = Fernet(os.environ['PASSWORD_ENCRYPT_KEY'].encode())
    email_password_encrypted = fernet.encrypt(email_password_raw.encode()).decode()

    # build SQL insert / update statement
    sql_insert = f"""
    INSERT INTO regions 
    SET team_id='{team_id}', workspace_name='{workspace_name}', bot_token='{bot_token}', email_enabled={email_enable}, email_server='{email_server}', 
        email_server_port={email_port}, email_user='{email_user}', email_password='{email_password_encrypted}', email_to='{email_to}', email_option_show={email_option_show}, postie_format={postie_format}
    ON DUPLICATE KEY UPDATE
        team_id='{team_id}', workspace_name='{workspace_name}', bot_token='{bot_token}', email_enabled={email_enable}, email_server='{email_server}', 
        email_server_port={email_port}, email_user='{email_user}', email_password='{email_password_encrypted}', email_to='{email_to}', email_option_show={email_option_show}, postie_format={postie_format}
    ;
    """

    # attempt update
    logging.info(f"Attempting SQL insert / update: {sql_insert}")
    try:
        with my_connect() as mydb:
            mycursor = mydb.conn.cursor()
            mycursor.execute(sql_insert)
            mycursor.execute("COMMIT;")
    except Exception as e:
        logging.error(f"Error writing to db: {e}")
        error_msg = e

slack_app.command("/config-slackblast")(
    ack=respond_to_slack_within_3_seconds,
    lazy=[config_slackblast]
)

# slack_app.command("/email-test")(
#     ack=respond_to_slack_within_3_seconds,
#     lazy=[email_test]
# )

slack_app.command("/slackblast")(
    ack=respond_to_slack_within_3_seconds,
    lazy=[command]
)

slack_app.command("/backblast")(
    ack=respond_to_slack_within_3_seconds,
    lazy=[command]
)

slack_app.command("/preblast")(
    ack=respond_to_slack_within_3_seconds,
    lazy=[command]
)

slack_app.command("/labs-slackblast")(
    ack=respond_to_slack_within_3_seconds,
    lazy=[command_labs]
)


@slack_app.view("backblast-id")
def view_submission(ack, body, logger, client, context):
    ack()
    team_id = context['team_id']
    bot_token = context['bot_token']

    result = body["view"]["state"]["values"]
    title = result["title"]["title"]["value"]
    date = result["date"]["datepicker-action"]["selected_date"]
    the_ao = result["the_ao"]["channels_select-action"]["selected_channel"]
    the_q = result["the_q"]["users_select-action"]["selected_user"]
    the_coq = result["the_coq"]["multi_users_select-action"]["selected_users"]
    pax = result["the_pax"]["multi_users_select-action"]["selected_users"]
    non_slack_pax = result["non_slack_pax"]["non_slack_pax-action"]["value"]
    fngs = result["fngs"]["fng-action"]["value"]
    count = result["count"]["count-action"]["value"]
    moleskine = result["moleskine"]["plain_text_input-action"]["value"]
    destination = result["destination"]["destination-input"]["selected_option"]["value"]
    email_send = safeget(result, "email_send", "email_send", "selected_option", "value")
    the_date = result["date"]["datepicker-action"]["selected_date"]

    # Check to see if email is enabled for the region
    try:
        with my_connect() as mydb:
            mycursor = mydb.conn.cursor()
            mycursor.execute(f'SELECT email_enabled, email_option_show FROM regions WHERE team_id = "{team_id}";')
            email_enabled, email_option_show = mycursor.fetchone()
            print(f'email_enabled: {email_enabled}')
    except Exception as e:
        logging.error(f"Error pulling user db email info: {e}")

    pax_names_list = get_user_names(pax, logger, client, return_urls=False) or ['']
    pax_formatted = get_pax(pax)
    pax_full_list = [pax_formatted]
    fngs_formatted = fngs
    if non_slack_pax != 'None':
        pax_full_list.append(non_slack_pax)
        pax_names_list.append(non_slack_pax)
    if fngs != 'None':
        pax_full_list.append(fngs)
        pax_names_list.append(fngs)
        fngs_formatted = str(fngs.count(',') + 1) + ' ' + fngs
    pax_formatted = ', '.join(pax_full_list)
    pax_names = ', '.join(pax_names_list)

    if the_coq == []:
        the_coqs_formatted = ''
        the_coqs_names = ''
    else:
        the_coqs_formatted = get_pax(the_coq)
        the_coqs_full_list = [the_coqs_formatted]
        the_coqs_names_list = get_user_names(the_coq, logger, client, return_urls=False)
        the_coqs_formatted = ', ' + ', '.join(the_coqs_full_list)
        the_coqs_names = ', ' + ', '.join(the_coqs_names_list)

    moleskine_formatted = parse_moleskin_users(moleskine, client)

    logger.info(result)

    chan = destination
    if chan == 'THE_AO':
        chan = the_ao

    logger.info('Channel to post to will be {} because the selected destination value was {} while the selected AO in the modal was {}'.format(
        chan, destination, the_ao))

    ao_name = get_channel_name(the_ao, logger, client)
    q_name, q_url = (get_user_names([the_q], logger, client, return_urls=True))
    q_name = (q_name or [''])[0]
    # print(f'CoQ: {the_coq}')
    q_url = q_url[0]

    msg = ""
    try:
        # formatting a message
        # todo: change to use json object
        header_msg = f"*Slackblast*: "
        title_msg = f"*" + title + "*"

        date_msg = f"*DATE*: " + the_date
        ao_msg = f"*AO*: <#" + the_ao + ">"
        q_msg = f"*Q*: <@" + the_q + ">" + the_coqs_formatted
        pax_msg = f"*PAX*: " + pax_formatted
        fngs_msg = f"*FNGs*: " + fngs_formatted
        count_msg = f"*COUNT*: " + count
        moleskine_msg = moleskine_formatted

        # Message the user via the app/bot name
        # if config('POST_TO_CHANNEL', cast=bool):
        body = make_body(date_msg, ao_msg, q_msg, pax_msg,
                            fngs_msg, count_msg, moleskine_msg)
        msg = header_msg + "\n" + title_msg + "\n" + body
        client.chat_postMessage(channel=chan, text=msg, username=f'{q_name} (via Slackblast)', icon_url=q_url)
        logger.info('\nMessage posted to Slack! \n{}'.format(msg))
    except Exception as slack_bolt_err:
        logger.error('Error with posting Slack message with chat_postMessage: {}'.format(
            slack_bolt_err))
        # Try again and bomb out without attempting to send email
        client.chat_postMessage(channel=chan, text='There was an error with your submission: {}'.format(slack_bolt_err))
    try:
        if (email_send and email_send == "yes") or (email_send is None and email_enabled == 1):
            # Pull email settings
            try:
                with my_connect() as mydb:
                    mycursor = mydb.conn.cursor()
                    mycursor.execute(f'SELECT email_server, email_server_port, email_user, email_password, email_to, postie_format FROM regions WHERE team_id = "{team_id}";')
                    email_server, email_server_port, email_user, email_password, email_to, postie_format = mycursor.fetchone()
            except Exception as e:
                logging.error(f"Error pulling user db email info: {e}")
            
            ao_title = (ao_name or '').replace('the', '').title()

            date_msg = f"DATE: " + the_date
            ao_msg = f"AO: " + (ao_name or '').replace('the', '').title()
            q_msg = f"Q: " + q_name + the_coqs_names
            pax_msg = f"PAX: " + pax_names
            fngs_msg = f"FNGs: " + fngs_formatted
            count_msg = f"COUNT: " + count
            moleskine_msg = moleskine.replace('*','')

            if postie_format:
                subject = f'[{ao_name}] {title}'
                moleskine_msg += f'\n\nTags: {ao_name}, {pax_names}'
            else:
                subject = title

            body_email = make_body(
                date_msg, ao_msg, q_msg, pax_msg, fngs_msg, count_msg, moleskine_msg
            )

            # Decrypt password
            fernet = Fernet(os.environ['PASSWORD_ENCRYPT_KEY'].encode())
            email_password_decrypted = fernet.decrypt(email_password.encode()).decode()

            sendmail.send(subject=subject, body=body_email, email_server=email_server, email_server_port=email_server_port, email_user=email_user, email_password=email_password_decrypted, email_to=email_to)

            logger.info('\nEmail Sent! \n{}'.format(body_email))
    # except UndefinedValueError as email_not_configured_error:
    #     logger.info('Skipping sending email since no EMAIL_USER or EMAIL_PWD found. {}'.format(
    #         email_not_configured_error))
    except Exception as sendmail_err:
        logger.error('Error with sendmail: {}'.format(sendmail_err))

@slack_app.view("backblast-id-labs")
def view_submission_labs(ack, body, logger, client, context):
    ack()
    team_id = context['team_id']
    bot_token = context['bot_token']

    result = body["view"]["state"]["values"]
    title = result["title"]["title"]["value"]
    date = result["date"]["datepicker-action"]["selected_date"]
    the_ao = result["the_ao"]["channels_select-action"]["selected_channel"]
    the_q = result["the_q"]["users_select-action"]["selected_user"]
    the_coq = result["the_coq"]["multi_users_select-action"]["selected_users"]
    pax = result["the_pax"]["multi_users_select-action"]["selected_users"]
    non_slack_pax = result["non_slack_pax"]["non_slack_pax-action"]["value"]
    fngs = result["fngs"]["fng-action"]["value"]
    count = result["count"]["count-action"]["value"]
    moleskine = result["moleskine"]["plain_text_input-action"]["value"]
    print(moleskine)
    destination = result["destination"]["destination-input"]["selected_option"]["value"]
    email_send = safeget(result, "email_send", "email_send", "selected_option", "value")
    the_date = result["date"]["datepicker-action"]["selected_date"]

    # Check to see if email is enabled for the region
    try:
        with my_connect() as mydb:
            mycursor = mydb.conn.cursor()
            mycursor.execute(f'SELECT email_enabled, email_option_show FROM regions WHERE team_id = "{team_id}";')
            email_enabled, email_option_show = mycursor.fetchone()
            print(f'email_enabled: {email_enabled}')
    except Exception as e:
        logging.error(f"Error pulling user db email info: {e}")

    pax_names_list = get_user_names(pax, logger, client, return_urls=False) or ['']
    pax_formatted = get_pax(pax)
    pax_full_list = [pax_formatted]
    fngs_formatted = fngs
    if non_slack_pax != 'None':
        pax_full_list.append(non_slack_pax)
        pax_names_list.append(non_slack_pax)
    if fngs != 'None':
        pax_full_list.append(fngs)
        pax_names_list.append(fngs)
        fngs_formatted = str(fngs.count(',') + 1) + ' ' + fngs
    pax_formatted = ', '.join(pax_full_list)
    pax_names = ', '.join(pax_names_list)

    if the_coq == []:
        the_coqs_formatted = ''
        the_coqs_names = ''
    else:
        the_coqs_formatted = get_pax(the_coq)
        the_coqs_full_list = [the_coqs_formatted]
        the_coqs_names_list = get_user_names(the_coq, logger, client, return_urls=False)
        the_coqs_formatted = ', ' + ', '.join(the_coqs_full_list)
        the_coqs_names = ', ' + ', '.join(the_coqs_names_list)

    moleskine_formatted = parse_moleskin_users(moleskine, client)

    logger.info(result)

    chan = destination
    if chan == 'THE_AO':
        chan = the_ao

    logger.info('Channel to post to will be {} because the selected destination value was {} while the selected AO in the modal was {}'.format(
        chan, destination, the_ao))

    ao_name = get_channel_name(the_ao, logger, client)
    q_name, q_url = (get_user_names([the_q], logger, client, return_urls=True))
    q_name = (q_name or [''])[0]
    # print(f'CoQ: {the_coq}')
    q_url = q_url[0]

    msg = ""
    try:
        # formatting a message
        # todo: change to use json object
        header_msg = f"*Slackblast*: "
        title_msg = f"*" + title + "*"

        edit_block = {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Edit this backblast",
                        "emoji": True
                    },
                    "value": "click_me_123",
                    "action_id": "edit-backblast"
                }
            ],
            "block_id": "edit-backblast"
        }

        date_msg = f"*DATE*: " + the_date
        ao_msg = f"*AO*: <#" + the_ao + ">"
        q_msg = f"*Q*: <@" + the_q + ">" + the_coqs_formatted
        pax_msg = f"*PAX*: " + pax_formatted
        fngs_msg = f"*FNGs*: " + fngs_formatted
        count_msg = f"*COUNT*: " + count
        moleskine_msg = moleskine_formatted

        # Message the user via the app/bot name
        # if config('POST_TO_CHANNEL', cast=bool):
        body = make_body(date_msg, ao_msg, q_msg, pax_msg,
                            fngs_msg, count_msg, moleskine_msg)
        msg = header_msg + "\n" + title_msg + "\n" + body

        msg_block = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": msg
            },
            "block_id": "msg_text"
        }

        # res = client.chat_postMessage(channel=chan, text=msg, username=f'{q_name} (via Slackblast)', icon_url=q_url)
        # edit_block['elements'][0]['value'] = res['ts']
        # client.chat_postMessage(channel=chan, text="slackblast_button", username=f'{q_name} (via Slackblast)', icon_url=q_url, blocks=[edit_block])
        res = client.chat_postMessage(channel=chan, text='slackblast_with_buttons', username=f'{q_name} (via Slackblast)', icon_url=q_url, blocks=[msg_block, edit_block])
        logger.info('\nMessage posted to Slack! \n{}'.format(msg))
    except Exception as slack_bolt_err:
        logger.error('Error with posting Slack message with chat_postMessage: {}'.format(
            slack_bolt_err))
        # Try again and bomb out without attempting to send email
        client.chat_postMessage(channel=chan, text='There was an error with your submission: {}'.format(slack_bolt_err))

@slack_app.action("edit-backblast")
def handle_edit_backblast(ack, body, client, logger, context):
    ack()
    logger.info(body)
    print(body)
    user_id = context["user_id"]
    team_id = context["team_id"]

    # backblast_ts = body['actions'][0]['value']
    backblast_channel = body['channel']['id']
    # res = client.conversations_history(channel=backblast_channel, lastest=backblast_ts, limit=2, inclusive=True)
    # print(res)
    # for message in res['messages']:
    #     if message['ts']==backblast_ts:
    #         text_og = message['text']

    # Pull backblast post and text
    text_og = body['message']['blocks'][0]['text']['text']
    backblast_ts = body['message']['ts']
    

    # Take out * and split by line
    text = text_og.replace('*','')
    fields = text.split('\n')

    # Start pulling fields
    # TODO: this code is highly dependent on a specific format used by slackblast - if this changes, the below will break
    # TODO: would be great to make it more resiliant in the future
    title = fields[1]
    date_str = fields[2][6:]
    ao_id = fields[3][6:-1]
    q_pax_id = fields[4][5:16]
    coq_list = fields[4][19:].replace('<@', '').replace(' ','').replace('>', '').split(',')
    if coq_list == ['']:
        coq_list = []

    # Generate FNG string / list
    i = 6
    try:
        while i <= len(fields[6]):
            fng_count = int(fields[6][i])
            i += 1
    except ValueError as e:
        if i>6:
            i += 1
    fng_list = fields[6][i:].split(', ')
    if len(fng_list) == 0:
        fng_str = 'None'
    else:
        fng_str = ', '.join(fng_list)

    # Generate slack PAX list
    pax_list = fields[5][5:].replace(' ','').split(',')
    pax_list = list(set(pax_list).difference(fng_list))
    slack_pax_list = [x for x in pax_list if x[:2]=='<@']
    slack_pax_list2 = [x.replace('<@','').replace('>','') for x in slack_pax_list]

    # Generate non-slack (non-FNG) list
    nonslack_pax_list = list(set(pax_list).difference(slack_pax_list))
    if len(nonslack_pax_list) == 0:
        nonslack_pax_str = 'None'
    else:
        nonslack_pax_str = ', '.join(nonslack_pax_list)

    # Pull counts and formatted moleskin
    pax_count = fields[7][7:]

    nl_count = 0
    nl_find = -1
    while nl_count <= 7:
        nl_find = text_og.find('\n', nl_find+1)
        nl_count += 1

    moleskin = text_og[nl_find:]

    blocks = [
        {
            "type": "input",
            "block_id": "title",
            "element": {
                "type": "plain_text_input",
                "action_id": "title",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Snarky Title?"
                },
                "initial_value": title
            },
            "label": {
                "type": "plain_text",
                "text": "Title"
            }
        },
        {
            "type": "input",
            "block_id": "the_ao",
            "element": {
                "type": "channels_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select the AO",
                    "emoji": True
                },
                "action_id": "channels_select-action",
                "initial_channel": ao_id
            },
            "label": {
                "type": "plain_text",
                "text": "The AO",
                "emoji": True
            }
        },
        {
            "type": "input",
            "block_id": "date",
            "element": {
                "type": "datepicker",
                "initial_date": date_str,
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select a date",
                    "emoji": True
                },
                "action_id": "datepicker-action"
            },
            "label": {
                "type": "plain_text",
                "text": "Workout Date",
                "emoji": True
            }
        },
        {
            "type": "input",
            "block_id": "the_q",
            "element": {
                "type": "users_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Tag the Q",
                    "emoji": True
                },
                "action_id": "users_select-action",
                "initial_user": q_pax_id
            },
            "label": {
                "type": "plain_text",
                "text": "The Q",
                "emoji": True
            }
        },
        {
            "type": "input",
            "block_id": "the_coq",
            "element": {
                "type": "multi_users_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Tag the CoQ(s)",
                    "emoji": True
                },
                "action_id": "multi_users_select-action"
            },
            "label": {
                "type": "plain_text",
                "text": "The CoQ(s), if applicable",
                "emoji": True
            },
            "optional": True
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "plain_text",
                    "text": "Note, only the first CoQ is tracked by PAXMiner",
                    "emoji": True
                }
            ]
        },
        {
            "type": "input",
            "block_id": "the_pax",
            "element": {
                "type": "multi_users_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Tag the PAX",
                    "emoji": True
                },
                "action_id": "multi_users_select-action",
                "initial_users": slack_pax_list2
            },
            "label": {
                "type": "plain_text",
                "text": "The PAX",
                "emoji": True
            }
        },
        {
            "type": "input",
            "block_id": "non_slack_pax",
            "element": {
                "type": "plain_text_input",
                "action_id": "non_slack_pax-action",
                "initial_value": nonslack_pax_str,
                "placeholder": {
                    "type": "plain_text",
                    "text": "Non-Slackers"
                }
            },
            "label": {
                "type": "plain_text",
                "text": "List untaggable PAX separated by commas (not including FNGs)"
            }
        },
        {
            "type": "input",
            "block_id": "fngs",
            "element": {
                "type": "plain_text_input",
                "action_id": "fng-action",
                "initial_value": fng_str,
                "placeholder": {
                    "type": "plain_text",
                    "text": "FNGs"
                }
            },
            "label": {
                "type": "plain_text",
                "text": "List FNGs separated by commas"
            }
        },
        {
            "type": "input",
            "block_id": "count",
            "element": {
                "type": "plain_text_input",
                "action_id": "count-action",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Total PAX count including FNGs"
                },
                "initial_value": pax_count
            },
            "label": {
                "type": "plain_text",
                "text": "Count"
            }
        },
        {
            "type": "input",
            "block_id": "moleskine",
            "element": {
                "type": "plain_text_input",
                "multiline": True,
                "action_id": "plain_text_input-action",
                "initial_value": moleskin,
                "placeholder": {
                    "type": "plain_text",
                    "text": "Tell us what happened\n\n"
                }
            },
            "label": {
                "type": "plain_text",
                "text": "The Moleskine",
                "emoji": True
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "plain_text",
                    "text": f"If trying to tag PAX in here, substitute _ for spaces and do not include titles in parenthesis (ie, @Moneyball not @Moneyball_(F3_STC)). Spelling is important, capitalization is not!\n\nPlease note that email is disabled for backblast updates.\n\n{backblast_channel},{backblast_ts}",
                    "emoji": True
                }
            ]
        }
    ]

    view = {
        "type": "modal",
        "callback_id": "edit-slackblast-modal",
        "title": {
            "type": "plain_text",
            "text": "Edit backblast"
        },
        "submit": {
            "type": "plain_text",
            "text": "Submit"
        },
        "blocks": blocks
    }

    res = client.views_open(
        trigger_id=body["trigger_id"],
        view=view,
    )
    logger.info(res)

@slack_app.view("edit-slackblast-modal")
def view_edit_submission(ack, body, logger, client, context):
    ack()
    team_id = context['team_id']
    bot_token = context['bot_token']

    print(body)

    result = body["view"]["state"]["values"]
    title = result["title"]["title"]["value"]
    date = result["date"]["datepicker-action"]["selected_date"]
    the_ao = result["the_ao"]["channels_select-action"]["selected_channel"]
    the_q = result["the_q"]["users_select-action"]["selected_user"]
    the_coq = result["the_coq"]["multi_users_select-action"]["selected_users"]
    pax = result["the_pax"]["multi_users_select-action"]["selected_users"]
    non_slack_pax = result["non_slack_pax"]["non_slack_pax-action"]["value"]
    fngs = result["fngs"]["fng-action"]["value"]
    count = result["count"]["count-action"]["value"]
    moleskine = result["moleskine"]["plain_text_input-action"]["value"]
    # destination = result["destination"]["destination-input"]["selected_option"]["value"]
    email_send = safeget(result, "email_send", "email_send", "selected_option", "value")
    the_date = result["date"]["datepicker-action"]["selected_date"]

    context_text = body['view']['blocks'][-1]['elements'][0]['text']
    message_channel, backblast_ts = context_text.split('\n\n')[-1].split(',')
    # Check to see if email is enabled for the region
    try:
        with my_connect() as mydb:
            mycursor = mydb.conn.cursor()
            mycursor.execute(f'SELECT email_enabled, email_option_show FROM regions WHERE team_id = "{team_id}";')
            email_enabled, email_option_show = mycursor.fetchone()
            print(f'email_enabled: {email_enabled}')
    except Exception as e:
        logging.error(f"Error pulling user db email info: {e}")

    pax_names_list = get_user_names(pax, logger, client, return_urls=False) or ['']
    pax_formatted = get_pax(pax)
    pax_full_list = [pax_formatted]
    fngs_formatted = fngs
    if non_slack_pax != 'None':
        pax_full_list.append(non_slack_pax)
        pax_names_list.append(non_slack_pax)
    if fngs != 'None':
        pax_full_list.append(fngs)
        pax_names_list.append(fngs)
        fngs_formatted = str(fngs.count(',') + 1) + ' ' + fngs
    pax_formatted = ', '.join(pax_full_list)
    pax_names = ', '.join(pax_names_list)

    if the_coq == []:
        the_coqs_formatted = ''
        the_coqs_names = ''
    else:
        the_coqs_formatted = get_pax(the_coq)
        the_coqs_full_list = [the_coqs_formatted]
        the_coqs_names_list = get_user_names(the_coq, logger, client, return_urls=False)
        the_coqs_formatted = ', ' + ', '.join(the_coqs_full_list)
        the_coqs_names = ', ' + ', '.join(the_coqs_names_list)

    moleskine_formatted = parse_moleskin_users(moleskine, client)

    logger.info(result)

    # chan = destination
    # if chan == 'THE_AO':
    #     chan = the_ao

    # logger.info('Channel to post to will be {} because the selected destination value was {} while the selected AO in the modal was {}'.format(
    #     chan, destination, the_ao))

    ao_name = get_channel_name(the_ao, logger, client)
    q_name, q_url = (get_user_names([the_q], logger, client, return_urls=True))
    q_name = (q_name or [''])[0]
    # print(f'CoQ: {the_coq}')
    q_url = q_url[0]

    msg = ""
    try:
        # formatting a message
        # todo: change to use json object
        header_msg = f"*Slackblast*: "
        title_msg = f"*" + title + "*"

        edit_block = {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Edit this backblast",
                        "emoji": True
                    },
                    "value": "click_me_123",
                    "action_id": "edit-backblast"
                }
            ],
            "block_id": "edit-backblast"
        }

        date_msg = f"*DATE*: " + the_date
        ao_msg = f"*AO*: <#" + the_ao + ">"
        q_msg = f"*Q*: <@" + the_q + ">" + the_coqs_formatted
        pax_msg = f"*PAX*: " + pax_formatted
        fngs_msg = f"*FNGs*: " + fngs_formatted
        count_msg = f"*COUNT*: " + count
        moleskine_msg = moleskine_formatted

        # Message the user via the app/bot name
        # if config('POST_TO_CHANNEL', cast=bool):
        body = make_body(date_msg, ao_msg, q_msg, pax_msg,
                            fngs_msg, count_msg, moleskine_msg)
        msg = header_msg + "\n" + title_msg + "\n" + body

        msg_block = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": msg
            },
            "block_id": "msg_text"
        }

        client.chat_update(channel=message_channel, ts=backblast_ts, text=msg, username=f'{q_name} (via Slackblast)', icon_url=q_url)
        logger.info('\nMessage posted to Slack! \n{}'.format(msg))
    except Exception as slack_bolt_err:
        logger.error('Error with updating Slack message with chat_postMessage: {}'.format(
            slack_bolt_err))
        # Try again and bomb out without attempting to send email
        client.chat_postMessage(channel=message_channel, text='There was an error with your submission: {}'.format(slack_bolt_err))

def make_body(date, ao, q, pax, fngs, count, moleskine):
    return date + \
        "\n" + ao + \
        "\n" + q + \
        "\n" + pax + \
        "\n" + fngs + \
        "\n" + count + \
        "\n" + moleskine

@slack_app.view("preblast-id")
def view_preblast_submission(ack, body, logger, client):
    ack()
    result = body["view"]["state"]["values"]
    title = result["title"]["title"]["value"]
    date = result["date"]["datepicker-action"]["selected_date"]
    the_time = result["time"]["time-action"]["value"]
    the_ao = result["the_ao"]["channels_select-action"]["selected_channel"]
    the_q = result["the_q"]["users_select-action"]["selected_user"]
    # the_coq = result["the_coq"]["multi_users_select-action"]["selected_user"]
    the_why = result["why"]["why-action"]["value"]
    coupon = result["coupon"]["coupon-action"]["value"]
    fngs = result["fngs"]["fng-action"]["value"]

    moleskine = result["moleskine"]["plain_text_input-action"]["value"]
    destination = result["destination"]["destination-input"]["selected_option"]["value"]
    email_to = safeget(result, "email", "email-action", "value")
    the_date = result["date"]["datepicker-action"]["selected_date"]

    logger.info(result)

    chan = destination
    if chan == 'THE_AO':
        chan = the_ao

    logger.info('Channel to post to will be {} because the selected destination value was {} while the selected AO in the modal was {}'.format(
        chan, destination, the_ao))

    ao_name = get_channel_name(the_ao, logger, client)
    q_name, q_url = (get_user_names([the_q], logger, client, return_urls=True))
    q_name = (q_name or [''])[0]
    q_url = q_url[0]

    # if the_coq == []:
    #     the_coqs_formatted = ''
    # else:
    #     the_coqs_formatted = get_pax(the_coq)
    #     the_coqs_full_list = [the_coqs_formatted]
    #     the_coqs_formatted = ', ' + ', '.join(the_coqs_full_list)

    msg = ""
    try:
        # formatting a message
        # todo: change to use json object
        header_msg = f"*Preblast: " + title + "*"
        date_msg = f"*Date*: " + the_date
        time_msg = f"*Time*: " + the_time
        ao_msg = f"*Where*: <#" + the_ao + ">"
        q_msg = f"*Q*: <@" + the_q + ">" # + the_coqs_formatted
        why_msg = f"*Why*: " + the_why
        coupon_msg = f"*Coupons*: " + coupon
        fngs_msg = f"*FNGs*: " + fngs
        moleskine_msg = moleskine

        # Message the user via the app/bot name
        # if config('POST_TO_CHANNEL', cast=bool):
        body_list = [date_msg, time_msg, ao_msg, q_msg]
        if the_why != 'None':
            body_list.append(why_msg)
        if coupon != 'None':
            body_list.append(coupon_msg)
        if fngs != 'None':
            body_list.append(fngs_msg)
        if moleskine != 'None':
            body_list.append(moleskine_msg)

        body = "\n".join(body_list)
        # body = make_preblast_body(date_msg, time_msg, ao_msg, q_msg, why_msg, coupon_msg,
        #                     fngs_msg, moleskine_msg)
        msg = header_msg + "\n" + body
        client.chat_postMessage(channel=chan, text=msg, username=f'{q_name} (via Slackblast)', icon_url=q_url)
        logger.info('\nMessage posted to Slack! \n{}'.format(msg))
    except Exception as slack_bolt_err:
        logger.error('Error with posting Slack message with chat_postMessage: {}'.format(
            slack_bolt_err))
        # Try again and bomb out without attempting to send email
        client.chat_postMessage(channel=chan, text='There was an error with your submission: {}'.format(slack_bolt_err))
    # try:
    #     if email_to and email_to != OPTIONAL_INPUT_VALUE:
    #         subject = title

    #         date_msg = f"DATE: " + the_date
    #         time_msg = f"TIME: " + the_time
    #         ao_msg = f"AO: " + (ao_name or '').replace('the', '').title()
    #         q_msg = f"Q: " + q_name
    #         why_msg = f"Why: " + pax_names
    #         coupon_msg = f"Coupon: " + coupon
    #         fngs_msg = f"FNGs: " + fngs
    #         moleskine_msg = moleskine

    #         body_email = make_preblast_body(date_msg, time_msg, ao_msg, q_msg, why_msg, coupon_msg,
    #                          fngs_msg, moleskine_msg)
    #         sendmail.send(subject=subject, recipient=email_to, body=body_email)

    #         logger.info('\nEmail Sent! \n{}'.format(body_email))
    # except UndefinedValueError as email_not_configured_error:
    #     logger.info('Skipping sending email since no EMAIL_USER or EMAIL_PWD found. {}'.format(
    #         email_not_configured_error))
    # except Exception as sendmail_err:
    #     logger.error('Error with sendmail: {}'.format(sendmail_err))


def make_preblast_body(date, time, ao, q, why, coupon, fngs, moleskine):
    return date + \
        "\n" + time + \
        "\n" + ao + \
        "\n" + q + \
        "\n" + why + \
        "\n" + coupon + \
        "\n" + fngs + \
        "\n" + moleskine


# @slack_app.options("es_categories")
# def show_categories(ack, body, logger):
#     ack()
#     lookup = body["value"]
#     filtered = [x for x in categories if lookup.lower() in x["name"].lower()]
#     output = formatted_categories(filtered)
#     options = output
#     logger.info(options)

#     ack(options=options)


def get_pax(pax):
    p = ""
    for x in pax:
        p += "<@" + x + "> "
    return p


def handler(event, context):
    print(f'Original event: {event}')
    print(f'Original context: {context}')
    # parsed_event = json.loads(event['body'])
    # team_id = parsed_event['team_id']
    # print(f'Team ID: {team_id}')
    slack_handler = SlackRequestHandler(app=slack_app)
    return slack_handler.handle(event, context)

