"""
Module registry. Adding a new feature = build a Module subclass and append
its class here. Settings reads this list to render the enable/disable UI.
"""
from modules.dashboard import DashboardModule
from modules.launchers import LaunchersModule
from modules.ai_agents import AIAgentsModule
from modules.links import LinksModule
from modules.documents import DocumentsModule
from modules.notes import NotesModule
from modules.templates import TemplatesModule
from modules.passwords import PasswordsModule
from modules.reviews import ReviewsModule
from modules.automation_scripts import AutomationScriptsModule
from modules.tasks import TasksModule
from modules.health import HealthModule
from modules.timers import TimersModule
from modules.focus_music import FocusMusicModule
from modules.news import NewsModule
from modules.notifications import NotificationsModule
from modules.settings import SettingsModule


MODULE_CLASSES = [
    # Workspace section
    DashboardModule,
    LaunchersModule,
    AIAgentsModule,
    LinksModule,
    DocumentsModule,
    NotesModule,
    TemplatesModule,
    PasswordsModule,
    ReviewsModule,
    AutomationScriptsModule,
    # Tools section
    TasksModule,
    HealthModule,
    TimersModule,
    FocusMusicModule,
    NewsModule,
    # System section
    NotificationsModule,
    SettingsModule,
]
