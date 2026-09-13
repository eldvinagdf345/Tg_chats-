from aiogram.fsm.state import State, StatesGroup


class AccountStates(StatesGroup):
    waiting_label          = State()
    waiting_api_id         = State()
    waiting_api_hash       = State()
    waiting_session_string = State()
    waiting_phone          = State()
    waiting_phone_code     = State()
    waiting_2fa_password   = State()


class InstructionsChatStates(StatesGroup):
    """Free-form chat where the account owner describes, in their own words,
    how the assistant should behave — replaces the old fixed questionnaire."""
    chatting = State()


class QuickSettingStates(StatesGroup):
    """Generic single-value editor for one hard-rule/timing setting at a
    time (stop-words, message limits, work hours, notify chat, delays...).
    Which setting is being edited is kept in FSM data under 'setting_key'."""
    waiting_value = State()


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


class CampaignStates(StatesGroup):
    waiting_goal   = State()
    waiting_mode   = State()
    confirming     = State()
