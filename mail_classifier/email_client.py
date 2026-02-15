"""
Email client module for Outlook interaction.
Handles fetching emails, grouping by conversation, and applying categories.

Decomposes get_emails() function from lines 109-169 of original mail_classification.py
"""

import win32com.client
import pythoncom
from datetime import timezone
from typing import Dict, List, Any, Optional
from .constants import OutlookFolders


class EmailClient:
    """Client for interacting with Microsoft Outlook via COM."""

    def __init__(self, outlook_config: Dict[str, Any]):
        """
        Initialize Outlook connection.
        Extracted from lines 20-22 of original script.

        Args:
            outlook_config: Outlook configuration (ai_trigger_category, done_marker_category)
        """
        # Initialize Outlook application and namespace
        self.outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        self.ai_category = outlook_config['ai_trigger_category']
        self.done_category = outlook_config['done_marker_category']

    def get_folder_by_name_or_number(self, folder_spec):
        """
        Get Outlook folder by name or number.
        NEW: Support for multiple folder types.

        Args:
            folder_spec: Folder name (str) or Outlook constant (int)
                        6 = Inbox, 5 = Sent Items, etc.

        Returns:
            Outlook folder object

        Raises:
            ValueError: If folder not found
        """
        if isinstance(folder_spec, int):
            try:
                return self.outlook.GetDefaultFolder(folder_spec)
            except Exception as e:
                raise ValueError(f"Could not get folder {folder_spec}: {e}")
        else:
            # Search for folder by name
            return self._find_folder_by_name(folder_spec)

    def _find_folder_by_name(self, folder_name: str):
        """
        Search for folder by name in all stores.

        Args:
            folder_name: Name of folder to find

        Returns:
            Outlook folder object

        Raises:
            ValueError: If folder not found
        """
        # Try default inbox store first
        try:
            inbox = self.outlook.GetDefaultFolder(OutlookFolders.INBOX)
            parent = inbox.Parent

            # Search in current store
            for folder in parent.Folders:
                if folder.Name.lower() == folder_name.lower():
                    return folder
        except Exception:
            pass

        # If not found, default to inbox
        try:
            if folder_name.lower() in ['inbox', 'boîte de réception']:
                return self.outlook.GetDefaultFolder(OutlookFolders.INBOX)
        except Exception as e:
            raise ValueError(f"Could not find folder '{folder_name}': {e}")

        raise ValueError(f"Folder '{folder_name}' not found")

    def get_emails_by_category(self, folder, category: str,
                               exclude_category: Optional[str] = None) -> List[Any]:
        """
        Fetch emails from folder matching category criteria.
        Extracted from lines 118-126 of original script.

        Args:
            folder: Outlook folder object
            category: Category to match
            exclude_category: Optional category to exclude

        Returns:
            List of Outlook message objects
        """
        emails = []
        for message in folder.Items:
            try:
                if category in message.Categories:
                    if exclude_category and exclude_category in message.Categories:
                        continue
                    emails.append(message)
            except Exception as e:
                # Skip messages that can't be accessed
                print(f"Warning: Could not access message: {e}")
                continue

        return emails

    def group_by_conversation(self, emails: List[Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group emails by ConversationID.
        Extracted from lines 127-151 of original script.

        Args:
            emails: List of Outlook message objects

        Returns:
            Dictionary mapping conversation_id -> list of email data dicts
        """
        conversations = {}

        for message in emails:
            try:
                conv_id = message.ConversationID

                if conv_id not in conversations:
                    conversations[conv_id] = []

                email_data = self.extract_email_data(message)
                conversations[conv_id].append(email_data)

            except Exception as e:
                print(f"Warning: Could not process message: {e}")
                continue

        return conversations

    def extract_email_data(self, message: Any) -> Dict[str, Any]:
        """
        Extract structured data from Outlook message object.
        Extracted from lines 131-151 of original script.

        Args:
            message: Outlook message object

        Returns:
            Dictionary with email data
        """
        # Lire le contenu du fichier (preserve comment from original line 64)
        try:
            recipients = [r.Name for r in message.Recipients]
            recipients_str = ', '.join(recipients) if recipients else 'None'
        except Exception:
            recipients_str = 'None'

        return {
            'subject': message.Subject,
            'sender_email': message.SenderEmailAddress,
            'sender_name': message.SenderName,
            'body': message.Body,
            'received_time': message.ReceivedTime.replace(tzinfo=timezone.utc),
            'recipients': recipients_str,
            'conversation_topic': message.ConversationTopic,
            'categories': message.Categories,  # NEW: Preserve existing categories
            'message_object': message  # NEW: Keep reference for applying categories
        }

    def merge_categories(self, existing_cats: str, new_cats: List[str]) -> str:
        """
        Merge existing and new categories.
        NEW: Implements requirements 6, 7, 8.

        Logic:
        - Keep all existing non-AI categories
        - Remove AI trigger category
        - Add new categories
        - Add done marker

        Args:
            existing_cats: Comma-separated existing categories
            new_cats: List of new categories to add

        Returns:
            Comma-separated merged categories
        """
        # Parse existing categories
        existing_set = set(c.strip() for c in existing_cats.split(',') if c.strip())

        # Remove AI trigger category
        existing_set.discard(self.ai_category)

        # Add new categories
        existing_set.update(new_cats)

        # Add done marker
        existing_set.add(self.done_category)

        # Return sorted comma-separated string
        return ','.join(sorted(existing_set))

    def apply_categories_to_conversation(self, folder, conversation_id: str,
                                        categories: List[str]):
        """
        Apply categories to all emails in a conversation.
        Extracted from lines 156-167 of original script.

        Args:
            folder: Outlook folder object
            conversation_id: Conversation ID
            categories: List of categories to apply
        """
        count = 0

        for message in folder.Items:
            try:
                if message.ConversationID == conversation_id:
                    # Get existing categories
                    existing = message.Categories if message.Categories else ""

                    # Merge with new categories
                    merged = self.merge_categories(existing, categories)

                    # Apply merged categories
                    message.Categories = merged
                    message.Save()
                    count += 1

            except Exception as e:
                print(f"Warning: Could not apply categories to message: {e}")
                continue

        print(f"Applied categories to {count} emails in conversation")
