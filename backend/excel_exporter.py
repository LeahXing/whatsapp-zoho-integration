"""
Excel Exporter Module.
Flattens structured records into multi-sheet Excel workbooks with word wrap and visual formatting.
"""

import os
from typing import Dict, List, Any
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.utils.cell import get_column_letter
import config

MessageType = Dict[str, Any]
GroupDataType = Dict[str, List[MessageType]]


class ExcelExporter:
    """Handles multi-sheet Excel formatting and data export operations for chat logs."""

    @staticmethod
    def save_to_excel(all_groups_data: GroupDataType, output_file: str = config.EXCEL_FILE) -> None:
        """Flattens schema messages and exports them into separate Excel worksheets."""
        if not all_groups_data:
            print("❌ No data collected to export.")
            return

        output_dir = os.path.dirname(os.path.abspath(output_file))
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        print(f"Saving extracted results to workbook: '{output_file}'...")
        
        try:
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                for group_name, messages in all_groups_data.items():
                    clean_name: str = group_name[:30].replace(":", "").replace("/", "").replace("\\", "")
                    
                    flattened_rows = []
                    for msg in messages:
                        meta = msg.get("messageMeta", {})
                        sender = msg.get("senderIdentity", {})
                        content = msg.get("messageContent", {})
                        moderation = msg.get("moderationState", {})
                        mentions = msg.get("groupMentions", {})
                        
                        flat_row = {
                            "chatId": msg.get("chatId"),
                            "groupName": msg.get("groupContext", {}).get("currentName"), 
                            "messageId": msg.get("messageId"),
                            "Date": msg.get("_displayDate"),
                            "Time (AM/PM)": msg.get("_displayTime"),
                            "unixTimestamp": meta.get("unixTimestamp"),
                            "messageType": meta.get("messageType"),
                            "isForwarded": meta.get("isForwarded"), 
                            "senderWhatsAppId": sender.get("whatsappId"),
                            "senderPushName": sender.get("pushName"),
                            "currentGroupRole": sender.get("currentGroupRole"),
                            "textContent": content.get("textContent"),
                            "mediaPath": msg.get("_mediaPath", ""),
                            "hasMediaAttached": content.get("hasMediaAttached"),
                            "hasLinkReferences": content.get("hasLinkReferences"),
                            "isPinnedMessage": moderation.get("isPinnedMessage"),
                            "pinnedByAdminId": moderation.get("pinnedByAdminId"),
                            "isAnnounceMessage": moderation.get("isAnnounceMessage"),
                            "hasExplicitMentions": mentions.get("hasExplicitMentions"),
                            "mentionedUserIds": ", ".join(mentions.get("mentionedUserIds", [])),
                            "isGroupMentionAll": mentions.get("isGroupMentionAll"),
                        }
                        flattened_rows.append(flat_row)

                    df = pd.DataFrame(flattened_rows) if flattened_rows else pd.DataFrame(columns=["chatId", "groupName", "messageId", "textContent"])
                    df.to_excel(writer, sheet_name=clean_name, index=False)

            ExcelExporter._apply_styling(output_file)
            print("🎉 Workbook export layout complete!")

        except PermissionError:
            print(f"\n❌ PERMISSION ERROR: Could not write to '{output_file}'. Close the spreadsheet if open.")
        except Exception as e:
            print(f"\n❌ Workbook export failed: {e}\n")

    @staticmethod
    def _apply_styling(file_path: str) -> None:
        """Formats headers, enables text word wrap, and auto-fits columns for best view."""
        wb: openpyxl.Workbook = openpyxl.load_workbook(file_path)
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, name="Calibri", size=11)
        cell_font = Font(name="Calibri", size=10)
        
        thin_border = Border(
            left=Side(style='thin', color='D3D3D3'), right=Side(style='thin', color='D3D3D3'),
            top=Side(style='thin', color='D3D3D3'), bottom=Side(style='thin', color='D3D3D3')
        )

        sheet: Worksheet
        for sheet in wb.worksheets:
            sheet.freeze_panes = "A2"
            
            # Format header row
            for cell in sheet[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            # Format data rows
            for row in sheet.iter_rows(min_row=2, max_row=sheet.max_row, min_col=1, max_col=sheet.max_column):
                for cell in row:
                    cell.font = cell_font
                    cell.border = thin_border
                    
                    col_idx = cell.column
                    # Columns 14 (textContent) and 15 (mediaPath) get left alignment, others centered
                    is_wrapped_col = col_idx in [14, 15]
                    cell.alignment = Alignment(
                        horizontal="left" if is_wrapped_col else "center", 
                        vertical="top", 
                        wrap_text=True
                    )

            # Standardize column spacing configurations
            for col in sheet.columns:
                col_idx = col[0].column
                col_letter: str = get_column_letter(col_idx)
                
                if col_letter == 'N':     # textContent
                    sheet.column_dimensions[col_letter].width = 50
                elif col_letter == 'O':   # mediaPath
                    sheet.column_dimensions[col_letter].width = 35
                else:
                    max_len = max(len(str(cell.value or '')) for cell in col)
                    sheet.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 25)

        wb.save(file_path)
