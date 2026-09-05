from aiogram.fsm.state import State, StatesGroup


class AccountStates(StatesGroup):
    waiting_label          = State()
    waiting_api_id         = State()
    waiting_api_hash       = State()
    waiting_session_string = State()


class AccountProfileStates(StatesGroup):
    """Sequential 'interview' the bot runs to build the communication
    profile for an account — style, boundaries, notifications, timing."""
    waiting_persona_name       = State()
    waiting_address_form       = State()
    waiting_tone               = State()
    waiting_message_length     = State()
    waiting_emoji              = State()
    waiting_literacy           = State()
    waiting_taboo_topics       = State()
    waiting_fallback           = State()
    waiting_stop_keywords      = State()
    waiting_msg_limit_dialogue = State()
    waiting_msg_limit_day      = State()
    waiting_work_hours         = State()
    waiting_notify_chat        = State()
    waiting_delay_range        = State()


class ParserStates(StatesGroup):
    waiting_channel_choice = State()
    waiting_channel_link   = State()
    waiting_topic_choice   = State()  # выбор темы форума
    waiting_mode_choice    = State()
    waiting_count          = State()
    waiting_date_from      = State()
    waiting_date_to        = State()
    confirming             = State()


class DialogueSetupStates(StatesGroup):
    waiting_contact         = State()
    waiting_goal            = State()
    waiting_opening_message = State()


class DraftEditStates(StatesGroup):
    waiting_new_text = State()
