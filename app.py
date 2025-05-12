import streamlit as st
import os
import tempfile
from datetime import datetime

# Importing helper functions from your original code files
# Note: You need to create processing_helpers.py first from your paste.txt file
from processing_helpers import (
    extract_all_page_text,
    get_all_the_scores_text, 
    extract_administrative_info_and_make_df,
    extract_test_data,
    classify_band,
    order_dataframe_by_uppercase_in_column,
    render_paginated_tables
)

# Initialize session state variables if they don't exist
if "docx_path" not in st.session_state:
    st.session_state["docx_path"] = None
if "pdf_path" not in st.session_state:
    st.session_state["pdf_path"] = None
if "generated" not in st.session_state:
    st.session_state["generated"] = False
if "admin_df" not in st.session_state:
    st.session_state["admin_df"] = None

# Page configuration
st.set_page_config(
    page_title="Assessment Report Generator",
    page_icon="📝",
    layout="centered",
    initial_sidebar_state="expanded"
)

def process_pdf_and_generate_reports(
    pdf_path,
    testing_observation,
    spl,
    vision_comment,
    teacher_input
):
    """Process the PDF and generate required reports"""
    try:
        # Step 1: Extract text
        with open(pdf_path, "rb") as f:
            pages = extract_all_page_text(f)
        
        lines_until_stop = get_all_the_scores_text(pages, "STANDARD SCORES DISCREPANCY Interpretation at")

        # Step 2: Admin and test info
        admin_df, tests_df, idx_when_scores_start = extract_administrative_info_and_make_df(lines_until_stop)
        new_lines_until_stop = lines_until_stop[idx_when_scores_start:]

        # Step 3: Test slices
        try:
            oral_index = new_lines_until_stop.index('Woodcock-Johnson IV Tests of Oral Language (Norms based on age 15-4)')
            achieve_index = new_lines_until_stop.index('Woodcock-Johnson IV Tests of Achievement Form A and Extended (Norms based on age 15-4)')
        except ValueError:
            st.error("Could not find expected test sections in the PDF. Please check the format.")
            return None, None

        oral_test_lines = new_lines_until_stop[oral_index:achieve_index]
        achieve_test_lines = new_lines_until_stop[achieve_index:]

        # Step 4: Extract and clean test data
        oral_df = extract_test_data(oral_test_lines)
        achievement_df = extract_test_data(achieve_test_lines)

        oral_df = order_dataframe_by_uppercase_in_column(oral_df, 'Test/Cluster')
        achievement_df = order_dataframe_by_uppercase_in_column(achievement_df, 'Test/Cluster')
        oral_df.rename(columns={'Test/Cluster': 'Test'}, inplace=True)
        achievement_df.rename(columns={'Test/Cluster': 'Test'}, inplace=True)

        # Step 5: Create banded bell curve report
        oral_df.title = "Woodcock-Johnson IV Tests of Oral Language"
        achievement_df.title = "Woodcock-Johnson IV Tests of Achievement"

        # Generate PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            bell_curve_path = tmp_pdf.name
            render_paginated_tables([oral_df, achievement_df], bell_curve_path, admin_df)

        # Step 6: Create DOCX report
        template_path = "Testing Template.docx"
        if not os.path.exists(template_path):
            st.error(f"Template file '{template_path}' not found. Please ensure it's in the same directory as this app.")
            return None, bell_curve_path

        # Import here to avoid circular imports
        from docxtpl import DocxTemplate
        template = DocxTemplate(template_path)
        
        # Prepare data for template
        oral_tests = oral_df[['SS', 'PR']].to_dict(orient='records') if not oral_df.empty else []
        achievement_tests = achievement_df[['SS', 'PR']].to_dict(orient='records') if not achievement_df.empty else []

        # Extract specific test scores and ranges
        # Oral language tests
        context = extract_ranges(oral_df, achievement_df)
        
        # Add base context
        context.update({
            'examiner_name': admin_df.at[0, 'Teacher'],
            'student_full_name': admin_df.at[0, 'Name'],
            'date_today': datetime.today().strftime("%m/%d/%Y"),
            'test_dates': [f"{row['Test Date']} ({row['Test Abbrev']})" for _, row in tests_df.iterrows()],
            'spl': spl,
            'testing_observation': testing_observation,
            'vision_comment': vision_comment,
            'teacher_input': teacher_input,
            'oral_tests': oral_tests,
            'achievement_tests': achievement_tests,
        })
        
        # Try to get student's first name
        try:
            context['student_name'] = admin_df.at[0, 'Name'].split(', ')[1]
        except (IndexError, AttributeError):
            context['student_name'] = admin_df.at[0, 'Name']  # Use full name if can't split properly

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_docx:
            docx_path = tmp_docx.name
            template.render(context)
            template.save(docx_path)
        
        return docx_path, bell_curve_path
    
    except Exception as e:
        st.error(f"Error generating reports: {str(e)}")
        return None, None

def extract_ranges(oral_df, achievement_df):
    """Extract test ranges from dataframes"""
    ranges = {}
    
    # Function to safely get ranges
    def get_range(df, test_name, column='SS'):
        score = df.loc[df['Test'].str.upper() == test_name.upper(), column]
        return classify_band(score.iloc[0]) if not score.empty else "N/A"
    
    # Oral language tests
    try:
        ranges['broad_oral_range'] = get_range(oral_df, "BROAD ORAL LANGUAGE")
        ranges['oral_expr_range'] = get_range(oral_df, "ORAL EXPRESSION")
        ranges['picture_vocab_range'] = get_range(oral_df, "PICTURE VOCABULARY")
        ranges['sentence_rep_range'] = get_range(oral_df, "SENTENCE REPETITION")
        ranges['listening_comp_range'] = get_range(oral_df, "LISTENING COMP")
        ranges['under_dir_range'] = get_range(oral_df, "UNDERSTANDING DIRECTIONS")
        ranges['oral_comp_range'] = get_range(oral_df, "ORAL COMPREHENSION")
    except Exception as e:
        st.warning(f"Some oral language test scores could not be extracted: {str(e)}")
    
    # Achievement tests
    try:
        ranges['bas_read_range'] = get_range(achievement_df, "BASIC READING SKILLS")
        ranges['let_word_range'] = get_range(achievement_df, "LETTER-WORD IDENTIFICATION")
        ranges['word_att_range'] = get_range(achievement_df, "WORD ATTACK")
        ranges['read_comp_range'] = get_range(achievement_df, "READING COMPREHENSION")
        ranges['pass_comp_range'] = get_range(achievement_df, "PASSAGE COMPREHENSION")
        ranges['read_recall_range'] = get_range(achievement_df, "READING RECALL")
        ranges['read_flu_range'] = get_range(achievement_df, "READING FLUENCY")
        ranges['oral_read_range'] = get_range(achievement_df, "ORAL READING")
        ranges['sent_read_flu_range'] = get_range(achievement_df, "SENTENCE READING FLUENCY")
        ranges['math_calc_range'] = get_range(achievement_df, "MATH CALCULATION SKILLS")
        ranges['calc_range'] = get_range(achievement_df, "CALCULATION")
        ranges['fact_flu_range'] = get_range(achievement_df, "MATH FACTS FLUENCY")
        ranges['mat_pro_solv_range'] = get_range(achievement_df, "MATH PROBLEM SOLVING")
        ranges['app_pro_range'] = get_range(achievement_df, "APPLIED PROBLEMS")
        ranges['mat_matr_range'] = get_range(achievement_df, "NUMBER MATRICES")
        ranges['writ_exp_range'] = get_range(achievement_df, "WRITTEN EXPRESSION")
        ranges['sent_writ_flu_range'] = get_range(achievement_df, "SENTENCE WRITING FLUENCY")
        ranges['writ_samp_range'] = get_range(achievement_df, "WRITING SAMPLES")
        ranges['spel_range'] = get_range(achievement_df, "SPELLING")
    except Exception as e:
        st.warning(f"Some achievement test scores could not be extracted: {str(e)}")
    
    return ranges

def main():
    """Main function for Streamlit app"""
    st.title("📝 Assessment Report Generator")
    st.markdown("Upload a scoring PDF and fill in the details below to generate student reports.")
    
    if "file_uploader_key" not in st.session_state:
        st.session_state.file_uploader_key = "file_uploader_1"
    
    if "form_key" not in st.session_state:
        st.session_state.form_key = "form_1"


    # Sidebar for progress tracking
    with st.sidebar:
        st.subheader("Progress")
        file_status = "✅ Uploaded" if "admin_df" in st.session_state and st.session_state["admin_df"] is not None else "❌ Not uploaded"
        st.write(f"PDF File: {file_status}")
        
        if "admin_df" in st.session_state and st.session_state["admin_df"] is not None:
            st.write("Student Information:")
            st.write(f"- Name: {st.session_state['admin_df'].at[0, 'Name']}")
            st.write(f"- Age: {st.session_state['admin_df'].at[0, 'Age']}")
            st.write(f"- Grade: {st.session_state['admin_df'].at[0, 'Grade']}")
    
    # Upload section
    uploaded_file = st.file_uploader(
    "Upload Score Report PDF",
    type=["pdf"],
    key=st.session_state.file_uploader_key
)

    col1, col2 = st.columns(2)
    
    # Reset button
    if col2.button("Reset All", type="secondary"):
        new_file_key = f"file_uploader_{datetime.now().timestamp()}"
        new_form_key = f"form_{datetime.now().timestamp()}"
        st.session_state.clear()
        st.session_state.file_uploader_key = new_file_key  # unique key
        st.session_state.form_key = new_form_key
        st.rerun()

    
    # Process uploaded file
    if uploaded_file is not None:
        try:
            with st.spinner("Processing PDF..."):
                # Extract the basic information
                pages = extract_all_page_text(uploaded_file)
                lines_until_stop = get_all_the_scores_text(pages, "STANDARD SCORES DISCREPANCY Interpretation at")
                admin_df, tests_df, _ = extract_administrative_info_and_make_df(lines_until_stop)
                
                # Store admin info in session state
                st.session_state["admin_df"] = admin_df
                
                # Display success message
                st.success(f"File uploaded successfully for {admin_df.at[0, 'Name']}")
                
                # Show preview of extracted information
                with st.expander("Preview Extracted Information"):
                    st.write("#### Administrative Information")
                    st.dataframe(admin_df)
                    
                    st.write("#### Tests Administered")
                    st.dataframe(tests_df)
        except Exception as e:
            st.error(f"Error processing PDF: {str(e)}")
    
    # Inputs for report generation
    st.subheader("Report Information")
    
    col1, col2 = st.columns(2)
    with col1:
        testing_observation = st.text_area("Testing Observations", height=100, key=st.session_state.form_key + "_testing_obs")
    with col2:
        spl = st.text_input("Student's Primary Language", key=st.session_state.form_key + "_spl")
    
    col1, col2 = st.columns(2)
    with col1:
        vision_comment = st.text_area("Vision/Hearing Screening Comments", height=100, key=st.session_state.form_key + "_vision_comment")
    with col2:
        teacher_input = st.text_area("Teacher Input", height=100, key=st.session_state.form_key + "_teacher_input")
    
    # Generate reports
    if uploaded_file and col1.button("Generate Reports", type="primary"):
        with st.spinner("Processing and generating reports..."):
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
                temp_path = f.name
                f.write(uploaded_file.getbuffer())
            
            # Process file
            docx_path, pdf_path = process_pdf_and_generate_reports(
                temp_path,
                testing_observation,
                spl,
                vision_comment,
                teacher_input
            )
            
            # Clean up
            try:
                os.unlink(temp_path)
            except:
                pass
            
            if docx_path and pdf_path:
                st.session_state["docx_path"] = docx_path
                st.session_state["pdf_path"] = pdf_path
                st.session_state["generated"] = True
                st.success("Reports generated successfully!")
            else:
                st.error("Failed to generate reports. Check the logs for details.")
    
    # Show download buttons if reports were generated
    if st.session_state.get("generated", False):
        st.subheader("Download Reports")
        col1, col2 = st.columns(2)
        
        with col1:
            with open(st.session_state["docx_path"], "rb") as f:
                st.download_button(
                    "⬇️ Download Word Report",
                    f,
                    file_name=f"Student_Report_{datetime.now().strftime('%Y%m%d')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="download_docx"
                )
        
        with col2:
            with open(st.session_state["pdf_path"], "rb") as f:
                st.download_button(
                    "⬇️ Download Bell Curve PDF",
                    f,
                    file_name=f"Bell_Curve_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    key="download_pdf"
                )

if __name__ == "__main__":
    main()