"""
Google Sheets Reader for SEO Data
"""

import os
import logging
import asyncio
from typing import Optional
import pandas as pd
import requests
import io
import re

import gspread
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


class SheetsReader:
    """Reader for Google Sheets SEO data"""
    
    def __init__(self, credentials_path: Optional[str] = None, sheet_url: Optional[str] = None):
        """Initialize Sheets reader"""
        self.client = None
        self.credentials_path = credentials_path
        self.sheet_url = sheet_url or os.getenv("SEO_SHEET_URL")
        
        if not self.sheet_url:
            logger.warning("SEO_SHEET_URL not configured")
        
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize Google Sheets client with credentials"""
        creds_path = self._find_credentials_path()
        
        if creds_path and os.path.exists(creds_path):
            try:
                logger.info(f"Loading Sheets credentials from: {creds_path}")
                credentials = service_account.Credentials.from_service_account_file(
                    creds_path,
                    scopes=[
                        "https://www.googleapis.com/auth/spreadsheets.readonly",
                        "https://www.googleapis.com/auth/drive.readonly"
                    ]
                )
                self.client = gspread.authorize(credentials)
                logger.info("Sheets client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Sheets client: {e}")
                self.client = None
        else:
            logger.warning("No credentials found, will use public CSV export")
            self.client = None
    
    def _find_credentials_path(self) -> Optional[str]:
        """Find credentials.json path"""
        if self.credentials_path:
            return self.credentials_path
        
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            return os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        root_creds = os.path.join(project_root, "credentials.json")
        if os.path.exists(root_creds):
            return root_creds
        
        return None
    
    def _normalize_column_name(self, col: str) -> str:
        """Normalize column name (lowercase, underscores)"""
        return col.strip().lower().replace(" ", "_").replace("-", "_")
    
    async def read_sheet(self, sheet_url: Optional[str] = None, worksheet_name: str = None) -> pd.DataFrame:
        """
        Read Google Sheet and convert to DataFrame
        
        Args:
            sheet_url: Google Sheet URL
            worksheet_name: Worksheet name (optional)
            
        Returns:
            pandas DataFrame with normalized column names
        """
        url = sheet_url or self.sheet_url
        if not url:
            raise ValueError("Sheet URL not provided")
        
        # Extract sheet ID
        match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
        if not match:
            raise ValueError(f"Invalid sheet URL: {url}")
        
        sheet_id = match.group(1)
        gid_match = re.search(r'[#&]gid=([0-9]+)', url)
        
        return await self._read_single_sheet(sheet_id, gid_match, worksheet_name, url)
    
    async def _read_single_sheet(self, sheet_id: str, gid_match, worksheet_name: str, url: str) -> pd.DataFrame:
        """Read a single worksheet"""
        # Try public CSV export first
        try:
            if gid_match:
                gid = gid_match.group(1)
                csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
            else:
                csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
            
            def _download_csv():
                response = requests.get(csv_url, timeout=30)
                response.raise_for_status()
                return response.text
            
            csv_data = await asyncio.to_thread(_download_csv)
            df = pd.read_csv(io.StringIO(csv_data))
            logger.info(f"Loaded sheet: {len(df)} rows")
            
        except Exception as e:
            # Fallback to authenticated access
            if self.client is None:
                raise ValueError(f"Failed to access sheet: {e}")
            
            logger.info("Trying authenticated access")
            
            def _read_sheet():
                sheet = self.client.open_by_url(url)
                worksheet = sheet.worksheet(worksheet_name or "Sheet1")
                return worksheet.get_all_records()
            
            data = await asyncio.to_thread(_read_sheet)
            df = pd.DataFrame(data)
            logger.info(f"Loaded sheet: {len(df)} rows")
        
        if df.empty:
            return pd.DataFrame()
        
        # Normalize column names
        df.columns = [self._normalize_column_name(col) for col in df.columns]
        return df
    

# Singleton instance
_sheets_reader: Optional[SheetsReader] = None


def get_sheets_reader() -> SheetsReader:
    """Get or create Sheets reader singleton"""
    global _sheets_reader
    if _sheets_reader is None:
        _sheets_reader = SheetsReader()
    return _sheets_reader
