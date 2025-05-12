import pdfplumber
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.image as mpimg
from datetime import datetime
import re
from matplotlib.backends.backend_pdf import PdfPages
import os

# Band colors
band_colors = {
    "Very Low": "#FF4C4C",      # Red
    "Low": "#FFA500",           # Orange
    "Low Average": "#FFFF66",   # Yellow
    "Average": "#66B2FF",       # Blue
    "High Average": "#00CED1",  # Cyan
    "Superior": "#32CD32"       # Green
}

# Extract text from all pages
def extract_all_page_text(file_obj):
    """Extract text from all pages of a PDF file"""
    all_page_lines = []
    try:
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                lines = text.strip().split('\n') if text else []
                all_page_lines.append(lines)
        return all_page_lines
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {str(e)}")

def get_all_the_scores_text(all_page_lines, stop_phrase):
    """Collect all text until stop phrase is found"""
    collected_lines = []
    for page in all_page_lines:
        for line in page:
            if stop_phrase in line:
                return collected_lines
            collected_lines.append(line)
    return collected_lines  # If phrase not found

def extract_administrative_info_and_make_df(lines):
    """Extract administrative info and create DataFrames"""
    basic_info = lines[1:10]  # Take the first few lines with admin info

    admin_data = {}
    test_dates = []
    test_names = []

    try:
        test_section_index = basic_info.index("TESTS ADMINISTERED")
        admin_lines = basic_info[:test_section_index]
        test_lines = basic_info[test_section_index+1:]

        # Separate test date lines from admin lines (look for date pattern with test abbrev)
        date_line_pattern = re.compile(r"(\d{2}/\d{2}/\d{4})\s+\(([^)]+)\)")

        for line in admin_lines:
            if "Name:" in line and "School:" in line:
                admin_data["Name"] = re.search(r"Name:\s*(.*?)\s+School:", line).group(1)
                admin_data['School'] = re.search(r"School:\s*(.*)", line).group(1)
            elif "Date of Birth:" in line and "Teacher:" in line:
                admin_data["Date of Birth"] = re.search(r"Date of Birth:\s*(.*?)\s+Teacher:", line).group(1)
                admin_data['Teacher'] = re.search(r"Teacher:\s*(.*)", line).group(1)
            elif "Age:" in line and "Grade:" in line:
                admin_data['Age'] = re.search(r"Age:\s*(.*?)\s+Grade:", line).group(1)
                admin_data['Grade'] = re.search(r"Grade:\s*(.*)", line).group(1)
            elif "Sex:" in line:
                admin_data['Sex'] = re.search(r"Sex:\s*(.*?)\s+ID:", line).group(1)
            elif "Date of Testing:" in line:
                match = date_line_pattern.search(line)
                if match:
                    test_dates.append((match.group(1), match.group(2)))

        # Check for any additional date lines
        for line in admin_lines:
            match = date_line_pattern.match(line)
            if match and (match.group(1), match.group(2)) not in test_dates:
                test_dates.append((match.group(1), match.group(2)))

        # Pair with test names
        for i, test_name in enumerate(test_lines):
            if i < len(test_dates):
                test_date, test_abbrev = test_dates[i]
                test_names.append({
                    "Test Date": test_date,
                    "Test Abbrev": test_abbrev,
                    "Test Name": test_name
                })

        admin_df = pd.DataFrame([admin_data])
        tests_df = pd.DataFrame(test_names)

        return admin_df, tests_df, 10  # Return index where scores start
    except Exception as e:
        raise Exception(f"Error extracting administrative information: {str(e)}")

def extract_test_data(test_list):
    """Extract SS and PR from test scores"""
    rows = []
    for line in test_list:
        tokens = line.strip().split()
        # Skip lines that are too short or clearly not test data
        if len(tokens) < 5:
            continue

        try:
            # Try to parse the last two tokens as integers for SS and PR
            ss = int(tokens[-2])
            pr = int(tokens[-1])

            # Assume test/cluster name is everything before the first number (W score)
            for i, token in enumerate(tokens):
                if token.replace('.', '', 1).isdigit():
                    name = ' '.join(tokens[:i])
                    break
            else:
                continue  # No number found; skip

            rows.append({'Test/Cluster': name, 'SS': ss, 'PR': pr})
        except (ValueError, IndexError):
            continue  # Not a valid test result line
    
    df = pd.DataFrame(rows)
    return df.drop_duplicates(subset=['Test/Cluster', 'SS', 'PR']) if not df.empty else df

def is_uppercase_value(value):
    """Check if value is uppercase (used to identify broad tests)"""
    try:
        return str(value).isupper()
    except AttributeError:
        return False

def order_dataframe_by_uppercase_in_column(df, column_name):
    """Order dataframe with uppercase values (broad tests) at the top"""
    if df.empty:
        return df
        
    uppercase_rows = df[df[column_name].apply(is_uppercase_value)]
    lowercase_rows = df[~df[column_name].apply(is_uppercase_value)]
    ordered_df = pd.concat([uppercase_rows, lowercase_rows], ignore_index=True)
    return ordered_df

def classify_band(ss):
    """Classify standard score into performance band"""
    try:
        ss = float(ss)
        if ss < 70:
            return "Very Low"
        elif ss < 80:
            return "Low"
        elif ss < 90:
            return "Low Average"
        elif ss < 110:
            return "Average"
        elif ss < 120:
            return "High Average"
        else:
            return "Superior"
    except (ValueError, TypeError):
        return "N/A"

def wrap_text(text, max_width):
    """Wrap text to specified width"""
    if not text:
        return ""
        
    words = str(text).split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line + word) + 1 <= max_width:
            current_line += (word + " ")
        else:
            lines.append(current_line.strip())
            current_line = word + " "
    lines.append(current_line.strip())
    return "\n".join(lines)

def create_band_table(df):
    """Create a band table for visualization"""
    assessment_name = getattr(df, "title", "Unknown Assessment")
    band_columns = list(band_colors.keys())
    table_data = []

    for _, row in df.iterrows():
        ss = row["SS"]
        band = classify_band(ss)
        wrapped_text = wrap_text(row["Test"], 15)  # Adjust for column width
        row_data = {
            "Composite": wrapped_text,
            **{col: ss if col == band else "" for col in band_columns}
        }
        table_data.append(row_data)
    return pd.DataFrame(table_data), assessment_name

def render_paginated_tables(dataframes, pdf_filename, admin_df, max_rows=10):
    """Render tables to PDF with pagination"""
    pdf = PdfPages(pdf_filename)
    row_height = 0.08
    title_spacing = 0.09
    header_height = 0.09
    date_str = datetime.today().strftime("%m/%d/%Y")
    is_first_page = True  # flag to track the first page
    
    def new_figure():
        """Create a new figure for the PDF"""
        f, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis("off")
        return f, ax
  
    def add_table_page(df_chunk, title, pdf, is_first_page=False):
        """Add a page with a table to the PDF"""
        fig, ax = new_figure()
        y_cursor = 0.95
        
        # Add header with student name and date
        try:
            header_text = f"{admin_df['Name'].iloc[0]}   Triennial Assessment".ljust(60) + date_str
        except:
            header_text = "Assessment Report".ljust(60) + date_str
        
        ax.text(0.05, y_cursor, header_text, ha="left", va="top", fontsize=10, fontweight="bold", family="monospace")
        y_cursor -= header_height
        
        # Add bell curve image on first page
        if is_first_page:
            # Check if the bell curve image exists
            image_path = "Screenshot 2025-05-06 210329.png"
            if os.path.exists(image_path):
                try:
                    # Read image
                    img = mpimg.imread(image_path)
                    
                    # Try a larger image height
                    image_height = 0.40  
                    image_width = image_height * (1078 / 526)  # maintains aspect ratio
                    
                    # Ensure it doesn't exceed page width
                    image_width = min(image_width, 0.9)  # cap at 90% page width
                    
                    x_center = 0.5
                    x0 = x_center - image_width / 2
                    x1 = x_center + image_width / 2
                    y1 = y_cursor
                    y0 = y_cursor - image_height
                    
                    xlim = ax.get_xlim()
                    ylim = ax.get_ylim()
                    
                    # Show image and restore layout
                    ax.imshow(img, extent=[x0, x1, y0, y1])
                    ax.set_xlim(xlim)
                    ax.set_ylim(ylim)
                    
                    # Adjust cursor for following elements
                    y_cursor = y0 - 0.06
                except Exception as e:
                    print(f"Error loading image: {str(e)}")
        
        # Add table title with extra spacing
        ax.text(0.5, y_cursor, title, ha="center", va="bottom", fontsize=14, weight="bold")
        y_cursor -= title_spacing
        
        # Create the table
        table = ax.table(
            cellText=df_chunk.values,
            colLabels=df_chunk.columns,
            cellLoc="center",
            loc="center",
            bbox=[0.05, y_cursor - row_height * len(df_chunk), 0.9, row_height * (len(df_chunk) + 1)]
        )

        # Set header background colors
        for col_idx, col_name in enumerate(df_chunk.columns):
            color = "#f0f0f0" if col_idx == 0 else band_colors.get(col_name, "white")
            table[(0, col_idx)].set_facecolor(color)

        # Color only filled-in cells
        for row_idx in range(1, len(df_chunk) + 1):  # +1 because row 0 is header
            for col_idx, col_name in enumerate(df_chunk.columns):
                cell_value = df_chunk.iloc[row_idx - 1, col_idx]
                if cell_value != "":
                    color = band_colors.get(col_name, "white")
                    table[(row_idx, col_idx)].set_facecolor(color)
                else:
                    table[(row_idx, col_idx)].set_facecolor("white")
                    
        table.auto_set_font_size(False)
        table.set_fontsize(6.5)
        pdf.savefig(fig, dpi=300, bbox_inches="tight")
        plt.close(fig)

    # Process each dataframe
    for df in dataframes:
        if df.empty:
            continue
            
        table_df, title = create_band_table(df)
        cols = ["Composite"] + list(band_colors.keys())
        table_df = table_df[cols]

        # Split into chunks of max_rows rows
        for start in range(0, len(table_df), max_rows):
            chunk = table_df.iloc[start:start + max_rows]
            add_table_page(chunk, title, pdf, is_first_page)
            is_first_page = False

    pdf.close()
    return pdf_filename