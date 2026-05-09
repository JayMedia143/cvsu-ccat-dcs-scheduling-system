# Detected Routes and Features

| URL Rule | Endpoint | Methods | Roles | Description |
| --- | --- | --- | --- | --- |
| `/` | `login` | `POST, GET` | `public` | No description available |
| `/add_user` | `add_user` | `POST` | `superadmin` | No description available |
| `/api/archive/capture` | `api_archive_capture` | `POST` | `admin, superadmin` | Performs the full-state cloning of current schedules into an archive snapshot. |
| `/api/archive/enter-snapshot/<int:archive_id>` | `api_archive_enter` | `GET` | `admin, superadmin` | Activates the system-wide read-only historical view for a specific snapshot. |
| `/api/archive/exit-snapshot` | `api_archive_exit` | `GET` | `admin, superadmin` | Exits historical view and returns the system to the active live state. |
| `/api/archive/export/<int:archive_id>` | `archive_export_excel` | `GET` | `admin, superadmin` | Exports a specific archive to a professional Excel report. |
| `/api/archive/reset-system` | `api_archive_reset` | `POST` | `superadmin` | Wipes the active operational data and prepares the system for a new term. |
| `/api/archive/stats` | `api_archive_stats` | `GET` | `admin, superadmin` | Returns counts of active entities for the archive summary modal. |
| `/api/audit/logic_ping` | `audit_logic_ping` | `GET` | `superadmin` | Diagnostic endpoint for the System Auditor to verify backend logic. |
| `/api/check-feasibility` | `check_feasibility` | `POST` | `admin, superadmin, user` | Rapid Greedy FFD check to determine if the rooms can handle the load. |
| `/api/conflicts/check` | `api_check_conflicts` | `GET` | `login_required` | Check if a specific day/time slot has room, faculty, or section conflicts. |
| `/api/courses-with-schedules` | `api_courses_with_schedules` | `GET` | `login_required` | Return courses that have scheduled classes for the given semester. |
| `/api/draft/<int:draft_id>` | `api_draft_delete` | `DELETE` | `login_required` | No description available |
| `/api/draft/<int:draft_id>` | `api_draft_edit` | `PATCH` | `login_required` | No description available |
| `/api/draft/<int:draft_id>/clone` | `api_draft_clone` | `POST` | `login_required` | Duplicates an existing draft version and its entries. |
| `/api/draft/<int:draft_id>/entities` | `api_draft_entities` | `GET` | `login_required` | Returns only the sections, faculty, and rooms that have entries in this draft. |
| `/api/draft/<int:draft_id>/entries` | `api_draft_entries` | `GET` | `login_required` | No description available |
| `/api/draft/<int:draft_id>/history` | `get_draft_history` | `GET` | `login_required` | No description available |
| `/api/draft/<int:draft_id>/publish` | `api_draft_publish` | `POST` | `login_required` | No description available |
| `/api/draft/create` | `api_draft_create` | `POST` | `login_required` | No description available |
| `/api/draft/snapshot` | `api_draft_snapshot` | `POST` | `login_required` | Clones all master schedule entries into a new draft version. |
| `/api/hub/chat` | `api_hub_chat` | `POST` | `login_required` | HTTP fallback for chat when WebSocket is disconnected. |
| `/api/hub/conversations` | `api_hub_conversations` | `GET` | `login_required` | Returns a list of unique users the current user has chatted with, plus a global Everyone card. |
| `/api/hub/decide/<int:draft_id>` | `api_hub_decide` | `POST` | `admin, superadmin` | Admin approves, rejects, or holds a proposal. |
| `/api/hub/drafts` | `api_hub_drafts` | `GET` | `login_required` | Returns drafts the current user can attach to a chat message. |
| `/api/hub/mark_read` | `api_hub_mark_read` | `POST` | `login_required` | No description available |
| `/api/hub/message/<int:msg_id>/delete` | `api_hub_message_delete` | `POST` | `login_required` | No description available |
| `/api/hub/message/<int:msg_id>/edit` | `api_hub_message_edit` | `POST` | `login_required` | No description available |
| `/api/hub/messages` | `api_hub_messages` | `GET` | `login_required` | Returns message history for a specific conversation. |
| `/api/hub/pending_drafts` | `api_hub_pending_drafts` | `GET` | `login_required` | No description available |
| `/api/hub/propose` | `api_hub_propose` | `POST` | `login_required` | Department Heads submit their draft for approval. |
| `/api/hub/user/<username>/history` | `api_hub_user_history` | `GET` | `login_required` | Returns all approved/rejected logs for a specific user. |
| `/api/hub/users` | `api_hub_users` | `GET` | `login_required` | Returns list of users this person can privately message. |
| `/api/irregular-batch` | `api_irregular_batch` | `POST` | `login_required` | No description available |
| `/api/irregular-confirm/<int:student_id>` | `api_irregular_confirm` | `POST` | `login_required` | No description available |
| `/api/irregular-pathfinder/<int:student_id>` | `api_irregular_pathfinder` | `POST` | `login_required` | No description available |
| `/api/layout-variables/<string:layout_type>` | `api_layout_variables` | `GET` | `login_required` | Return all available {{variables}} for a given layout type (section/faculty/room/course). |
| `/api/move-class` | `api_move_class` | `POST` | `login_required` | No description available |
| `/api/notifications` | `get_notifications` | `GET` | `login_required` | No description available |
| `/api/notifications/mark-read` | `mark_notifications_read` | `POST` | `login_required` | No description available |
| `/api/prefix-courses` | `api_prefix_courses` | `GET` | `admin, superadmin` | AJAX: return courses matching a prefix or exact code. |
| `/api/preview-conflicts` | `api_preview_conflicts` | `GET` | `admin, superadmin` | Pre-compute conflict level for every possible drop position for a class. |
| `/api/room-utilization` | `api_room_utilization` | `GET` | `admin, superadmin` | Return per-room utilization stats based on currently saved ScheduledClasses. |
| `/api/rooms-with-schedules` | `api_rooms_with_schedules` | `GET` | `login_required` | Return rooms that have scheduled classes for the given semester. |
| `/api/schedule/<int:sched_id>` | `api_delete_schedule` | `DELETE` | `login_required` | Delete a schedule entry. Guards: |
| `/api/schedule/<int:sched_id>` | `api_patch_schedule` | `PATCH` | `login_required` | Update an existing schedule entry's faculty, room, day, time, session_type. |
| `/api/schedule/add` | `api_add_schedule` | `POST` | `login_required` | Manually add a new schedule entry. Admins can add to master directly. |
| `/api/schedule/entries` | `api_schedule_entries` | `GET` | `login_required` | Return master (is_draft=False) ScheduledClass entries for the editor grid. |
| `/api/sections-with-schedules` | `api_sections_with_schedules` | `GET` | `login_required` | Return sections that have scheduled classes for the given semester. |
| `/api/settings/schedule-lock` | `toggle_schedule_lock` | `POST` | `admin, superadmin` | No description available |
| `/api/user/check-feasibility` | `api_user_check_feasibility` | `POST` | `login_required` | Departmental capacity assessment for the User role. |
| `/api/user/generate` | `api_user_generate` | `POST` | `login_required` | Starts the departmental auto-scheduling process (User Role). |
| `/api/user/status` | `api_user_status` | `GET` | `login_required` | No description available |
| `/api/user/stop` | `api_user_stop` | `POST` | `login_required` | No description available |
| `/archive/semester` | `archive_semester` | `POST` | `admin, superadmin` | No description available |
| `/archives/delete/<int:archive_id>` | `archive_delete` | `POST` | `admin, superadmin` | Permanently removes an entire snapshot snapshot. |
| `/change_password` | `change_password` | `POST` | `login_required` | No description available |
| `/change_username` | `change_username` | `POST` | `login_required` | No description available |
| `/check-constraints` | `check_constraints` | `GET` | `admin, superadmin` | No description available |
| `/course-timetable-excel/<int:course_id>` | `course_timetable_excel` | `GET` | `login_required` | No description available |
| `/course-timetable-html/<int:course_id>` | `course_timetable_html` | `GET` | `login_required` | No description available |
| `/dashboard` | `dashboard` | `GET` | `admin, superadmin, user` | No description available |
| `/delete-layout/<layout_type>` | `delete_layout` | `POST` | `admin, superadmin` | Delete saved layout files (xlsx + state json) for a given type. |
| `/delete_user/<int:user_id>` | `delete_user` | `POST` | `superadmin` | No description available |
| `/download/curriculum-template` | `download_curriculum_template` | `GET` | `admin, superadmin` | No description available |
| `/download/faculty-loading-template` | `download_faculty_loading_template` | `GET` | `admin, superadmin` | No description available |
| `/download/student-template` | `download_student_template` | `GET` | `admin, superadmin` | No description available |
| `/export/excel_bulk` | `export_excel_bulk` | `GET` | `admin, superadmin` | No description available |
| `/faculty-timetable-excel/<int:faculty_id>` | `faculty_timetable_excel` | `GET` | `login_required` | No description available |
| `/faculty-timetable-html/<int:faculty_id>` | `faculty_timetable_html` | `GET` | `login_required` | No description available |
| `/generate` | `generate_page` | `GET` | `admin, superadmin, user` | No description available |
| `/get-generation-status` | `get_generation_status` | `GET` | `admin, superadmin` | No description available |
| `/get-schedule-grid/<string:view_type>/<int:entity_id>` | `get_schedule_grid` | `GET` | `login_required` | No description available |
| `/get_section_courses/<int:section_id>` | `get_section_courses` | `GET` | `admin, superadmin` | No description available |
| `/import-courses-pdf` | `import_courses_pdf` | `POST` | `admin, superadmin` | No description available |
| `/import_courses_docx` | `import_courses_docx` | `POST` | `admin, superadmin` | No description available |
| `/import_faculty_loading` | `import_faculty_loading` | `POST` | `admin, superadmin` | No description available |
| `/import_students_xlsx` | `import_students_xlsx` | `POST` | `admin, superadmin` | No description available |
| `/irregular-pathfinder/<int:student_id>` | `irregular_pathfinder` | `GET` | `login_required` | No description available |
| `/irregular-timetable/<string:student_id>` | `irregular_timetable_html` | `GET` | `public` | Render an irregular student's custom mixed schedule using the section template. |
| `/logout` | `logout` | `GET` | `public` | No description available |
| `/manage/archive/delete/<int:archive_id>` | `delete_archive` | `POST` | `admin, superadmin` | No description available |
| `/manage/archives` | `manage_archives` | `GET` | `admin, superadmin` | No description available |
| `/manage/archives/bulk_delete` | `bulk_delete_archives` | `POST` | `admin, superadmin` | No description available |
| `/manage/constraints` | `manage_constraints` | `POST, GET` | `admin, superadmin` | No description available |
| `/manage/constraints/sync` | `sync_constraints` | `POST` | `admin, superadmin` | Upserts the master constraint list into the DB. |
| `/manage/course/add` | `add_course` | `POST` | `login_required` | No description available |
| `/manage/course/archive/<int:course_id>` | `archive_course` | `POST` | `login_required` | No description available |
| `/manage/course/delete/<int:course_id>` | `delete_course` | `POST` | `login_required` | No description available |
| `/manage/course/restore/<int:course_id>` | `restore_course` | `POST` | `login_required` | No description available |
| `/manage/course/update/<int:course_id>` | `update_course` | `POST` | `login_required` | No description available |
| `/manage/courses` | `manage_courses` | `GET` | `login_required` | No description available |
| `/manage/courses/archive` | `courses_archive` | `GET` | `login_required` | No description available |
| `/manage/courses/bulk_archive` | `bulk_archive_courses` | `POST` | `login_required` | No description available |
| `/manage/courses/bulk_delete` | `bulk_delete_courses` | `POST` | `login_required` | No description available |
| `/manage/courses/bulk_restore` | `bulk_restore_courses` | `POST` | `login_required` | No description available |
| `/manage/courses/code-assignment` | `course_code_assignment` | `GET` | `admin, superadmin` | No description available |
| `/manage/courses/code-assignment/archive/<int:rule_id>` | `archive_code_rule` | `POST` | `admin, superadmin` | No description available |
| `/manage/courses/code-assignment/archived` | `code_rules_archive` | `GET` | `admin, superadmin` | No description available |
| `/manage/courses/code-assignment/bulk-delete` | `bulk_delete_code_rules` | `POST` | `admin, superadmin` | No description available |
| `/manage/courses/code-assignment/bulk-restore` | `bulk_restore_code_rules` | `POST` | `admin, superadmin` | No description available |
| `/manage/courses/code-assignment/delete-forever/<int:rule_id>` | `delete_code_rule_forever` | `POST` | `admin, superadmin` | No description available |
| `/manage/courses/code-assignment/reset` | `reset_code_assignment` | `POST` | `admin, superadmin` | No description available |
| `/manage/courses/code-assignment/restore/<int:rule_id>` | `restore_code_rule` | `POST` | `admin, superadmin` | No description available |
| `/manage/courses/code-assignment/save` | `save_code_assignment` | `POST` | `admin, superadmin` | No description available |
| `/manage/departments` | `manage_departments` | `GET` | `admin, superadmin` | No description available |
| `/manage/departments/add` | `add_department` | `POST` | `admin, superadmin` | No description available |
| `/manage/departments/archive` | `departments_archive` | `GET` | `admin, superadmin` | No description available |
| `/manage/departments/archive/<int:dept_id>` | `archive_department` | `POST` | `admin, superadmin` | No description available |
| `/manage/departments/bulk-archive` | `bulk_archive_departments` | `POST` | `admin, superadmin` | No description available |
| `/manage/departments/bulk-delete` | `bulk_delete_departments_permanent` | `POST` | `admin, superadmin` | No description available |
| `/manage/departments/bulk-restore` | `bulk_restore_departments` | `POST` | `admin, superadmin` | No description available |
| `/manage/departments/delete-permanent/<int:dept_id>` | `delete_department_permanent` | `POST` | `admin, superadmin` | No description available |
| `/manage/departments/restore/<int:dept_id>` | `restore_department` | `POST` | `admin, superadmin` | No description available |
| `/manage/departments/update/<int:dept_id>` | `update_department` | `POST` | `admin, superadmin` | No description available |
| `/manage/faculty` | `manage_faculty` | `GET` | `login_required` | No description available |
| `/manage/faculty/add` | `add_faculty` | `POST` | `login_required` | No description available |
| `/manage/faculty/archive` | `faculty_archive` | `GET` | `login_required` | No description available |
| `/manage/faculty/archive/<int:faculty_id>` | `archive_faculty` | `POST` | `login_required` | No description available |
| `/manage/faculty/bulk_archive` | `bulk_archive_faculty` | `POST` | `login_required` | No description available |
| `/manage/faculty/bulk_delete` | `bulk_delete_faculty` | `POST` | `login_required` | No description available |
| `/manage/faculty/bulk_restore` | `bulk_restore_faculty` | `POST` | `login_required` | No description available |
| `/manage/faculty/delete/<int:faculty_id>` | `delete_faculty` | `POST` | `login_required` | No description available |
| `/manage/faculty/quick-add-tba` | `quick_add_tba_faculty` | `POST` | `login_required` | No description available |
| `/manage/faculty/restore/<int:faculty_id>` | `restore_faculty` | `POST` | `login_required` | No description available |
| `/manage/faculty/save_assignments/<int:faculty_id>` | `save_faculty_assignments` | `POST` | `admin, superadmin, user` | No description available |
| `/manage/faculty/set_teachable_courses/<int:faculty_id>` | `set_teachable_courses` | `POST` | `admin, superadmin` | No description available |
| `/manage/faculty/update/<int:faculty_id>` | `update_faculty` | `POST` | `login_required` | No description available |
| `/manage/irregular-students` | `manage_irregular` | `GET` | `admin, superadmin` | No description available |
| `/manage/layouts` | `manage_layouts` | `POST, GET` | `admin, superadmin` | No description available |
| `/manage/layouts/upload_template` | `upload_template` | `POST` | `admin, superadmin` | No description available |
| `/manage/pre-assignment/add` | `add_preassignment` | `POST` | `admin, superadmin` | No description available |
| `/manage/pre-assignment/archive/<int:pa_id>` | `archive_preassignment` | `POST` | `admin, superadmin` | No description available |
| `/manage/pre-assignment/delete/<int:pa_id>` | `delete_preassignment` | `POST` | `admin, superadmin` | No description available |
| `/manage/pre-assignment/restore/<int:pa_id>` | `restore_preassignment` | `POST` | `admin, superadmin` | No description available |
| `/manage/pre-assignments` | `manage_preassignments` | `GET` | `admin, superadmin` | No description available |
| `/manage/pre-assignments/archive` | `preassignments_archive` | `GET` | `admin, superadmin` | No description available |
| `/manage/preassignments/bulk_archive` | `bulk_archive_preassignments` | `POST` | `admin, superadmin` | No description available |
| `/manage/preassignments/bulk_delete` | `bulk_delete_preassignments` | `POST` | `admin, superadmin` | No description available |
| `/manage/preassignments/bulk_restore` | `bulk_restore_preassignments` | `POST` | `admin, superadmin` | No description available |
| `/manage/room/<int:room_id>/special-courses` | `save_room_special_courses` | `POST` | `admin, superadmin` | No description available |
| `/manage/room/add` | `add_room` | `POST` | `login_required` | No description available |
| `/manage/room/archive/<int:room_id>` | `archive_room` | `POST` | `login_required` | No description available |
| `/manage/room/delete/<int:room_id>` | `delete_room` | `POST` | `login_required` | No description available |
| `/manage/room/quick-add-tba` | `quick_add_tba_room` | `POST` | `login_required` | No description available |
| `/manage/room/restore/<int:room_id>` | `restore_room` | `POST` | `login_required` | No description available |
| `/manage/room/update/<int:room_id>` | `update_room` | `POST` | `login_required` | No description available |
| `/manage/rooms` | `manage_rooms` | `GET` | `login_required` | No description available |
| `/manage/rooms/archive` | `rooms_archive` | `GET` | `login_required` | No description available |
| `/manage/rooms/bulk_archive` | `bulk_archive_rooms` | `POST` | `login_required` | No description available |
| `/manage/rooms/bulk_delete` | `bulk_delete_rooms` | `POST` | `login_required` | No description available |
| `/manage/rooms/bulk_restore` | `bulk_restore_rooms` | `POST` | `login_required` | No description available |
| `/manage/section/add` | `add_section` | `POST` | `admin, superadmin` | No description available |
| `/manage/section/archive/<int:section_id>` | `archive_section` | `POST` | `admin, superadmin` | No description available |
| `/manage/section/delete/<int:section_id>` | `delete_section` | `POST` | `admin, superadmin` | No description available |
| `/manage/section/restore/<int:section_id>` | `restore_section` | `POST` | `login_required` | No description available |
| `/manage/section/update/<int:section_id>` | `update_section` | `POST` | `admin, superadmin` | No description available |
| `/manage/sections` | `manage_sections` | `GET` | `login_required` | No description available |
| `/manage/sections/archive` | `sections_archive` | `GET` | `login_required` | No description available |
| `/manage/sections/bulk_archive` | `bulk_archive_sections` | `POST` | `login_required` | No description available |
| `/manage/sections/bulk_assign` | `bulk_assign_curriculum` | `POST` | `admin, superadmin` | No description available |
| `/manage/sections/bulk_delete` | `bulk_delete_sections` | `POST` | `login_required` | No description available |
| `/manage/sections/bulk_restore` | `bulk_restore_sections` | `POST` | `login_required` | No description available |
| `/manage/student/add` | `add_student` | `POST` | `admin, superadmin` | No description available |
| `/manage/student/archive/<int:student_pk>` | `archive_student` | `POST` | `admin, superadmin` | No description available |
| `/manage/student/delete/<int:student_pk>` | `delete_student` | `POST` | `admin, superadmin` | No description available |
| `/manage/student/restore/<int:student_pk>` | `restore_student` | `POST` | `admin, superadmin` | No description available |
| `/manage/student/toggle-irregular/<int:student_id>` | `toggle_irregular` | `POST` | `login_required` | No description available |
| `/manage/student/update/<int:student_pk>` | `update_student` | `POST` | `admin, superadmin` | No description available |
| `/manage/students` | `manage_students` | `GET` | `admin, superadmin` | No description available |
| `/manage/students/archive` | `students_archive` | `GET` | `admin, superadmin` | No description available |
| `/manage/students/bulk_archive` | `bulk_archive_students` | `POST` | `admin, superadmin` | No description available |
| `/manage/students/bulk_delete` | `bulk_delete_students` | `POST` | `admin, superadmin` | No description available |
| `/manage/students/bulk_restore` | `bulk_restore_students` | `POST` | `admin, superadmin` | No description available |
| `/manage/user/archive/<int:user_id>` | `archive_user` | `POST` | `superadmin` | No description available |
| `/manage/user/permanent_delete/<int:user_id>` | `permanent_delete_user` | `POST` | `superadmin` | No description available |
| `/manage/user/reset_password/<int:user_id>` | `reset_user_password` | `POST` | `superadmin` | No description available |
| `/manage/user/restore/<int:user_id>` | `restore_user` | `POST` | `superadmin` | No description available |
| `/manage/users/bulk_archive` | `bulk_archive_users` | `POST` | `superadmin` | No description available |
| `/manage/users/bulk_permanent_delete` | `bulk_permanent_delete_users` | `POST` | `superadmin` | No description available |
| `/manage/users/bulk_restore` | `bulk_restore_users` | `POST` | `superadmin` | No description available |
| `/manage/year/assign_courses/<int:year_level>` | `assign_courses_to_year` | `POST` | `admin, superadmin` | No description available |
| `/manage_users` | `manage_users` | `GET` | `superadmin` | No description available |
| `/manage_users/recycle_bin` | `users_recycle_bin` | `GET` | `superadmin` | No description available |
| `/monitoring` | `monitoring` | `GET` | `superadmin` | Renders the Bantay-System Monitoring Dashboard. |
| `/pending-room/run` | `run_pending_rooms` | `POST` | `admin, superadmin` | No description available |
| `/pending-sections` | `pending_sections` | `GET` | `admin, superadmin` | No description available |
| `/pending-sections/run` | `run_pending_sections` | `POST` | `admin, superadmin` | No description available |
| `/preview-layout/<layout_type>` | `preview_layout` | `GET` | `admin, superadmin` | Render the uploaded XLSX template as a standalone A4-paper HTML page. |
| `/proposal-hub` | `proposal_hub` | `GET` | `login_required` | Main view for the Centralized Proposal Terminal & Decision Hub. |
| `/public-student-schedule-excel/<string:student_id>` | `public_student_schedule_excel` | `GET` | `public` | No description available |
| `/public/archived-timetable-html/<int:archive_id>/<string:student_id>` | `public_archived_timetable_html` | `GET` | `public` | Specialized renderer for historical student schedules from snapshots. |
| `/public/section-timetable/<int:section_id>` | `public_section_timetable` | `GET` | `public` | Same as section_timetable_html but publicly accessible (no login required). |
| `/public/student-timetable-html/<string:identifier>` | `public_student_timetable_html` | `GET` | `public` | Publicly accessible route for the Student Portal and Admin viewer. |
| `/reports` | `reports_page` | `GET` | `admin, superadmin` | No description available |
| `/reports/clean-archives` | `clean_archives_page` | `GET` | `admin, superadmin` | No description available |
| `/resolve-unassigned` | `pending_faculty` | `GET` | `admin, superadmin` | No description available |
| `/resolve-unassigned/run` | `run_unassigned_resolver` | `POST` | `admin, superadmin` | No description available |
| `/room-timetable-excel/<int:room_id>` | `room_timetable_excel` | `GET` | `login_required` | No description available |
| `/room-timetable-html/<int:room_id>` | `room_timetable_html` | `GET` | `login_required` | No description available |
| `/save-layout-xlsx` | `save_layout_xlsx` | `POST` | `admin, superadmin` | Save only the XLSX template file (may laman ang image). Separate request para maiwasan ang 413. |
| `/schedule-editor` | `schedule_editor` | `GET` | `login_required` | No description available |
| `/schedule-issues` | `pending_room` | `GET` | `admin, superadmin` | No description available |
| `/section-timetable-excel/<int:section_id>` | `section_timetable_excel` | `GET` | `login_required` | No description available |
| `/section-timetable-html/<int:section_id>` | `section_timetable_html` | `GET` | `login_required` | Render a section's scheduled classes into the uploaded Excel template. |
| `/set-department-filter/<dept_name>` | `set_department_filter` | `GET` | `login_required` | No description available |
| `/set-semester-filter/<semester_name>` | `set_semester_filter` | `GET` | `login_required` | No description available |
| `/settings` | `save_settings` | `POST` | `admin, superadmin` | No description available |
| `/signup` | `signup` | `POST, GET` | `login_required` | No description available |
| `/start-generation` | `start_generation` | `POST` | `admin, superadmin, user` | No description available |
| `/stop-generation` | `stop_generation` | `POST` | `admin, superadmin` | No description available |
| `/student-portal` | `student_portal` | `POST, GET` | `public` | No description available |
| `/student-schedule/<string:student_id>` | `student_schedule` | `GET` | `public` | No description available |
| `/student-timetable-html/<int:student_pk>` | `student_timetable_html` | `GET` | `public` | Unified route to render a student's schedule. |
| `/system-tester` | `system_tester` | `GET` | `superadmin` | Standalone Audit Console: Verifies all 12 Phases of the Master Manifest. |
| `/update-manual-schedule` | `update_manual_schedule` | `POST` | `admin, superadmin` | No description available |
| `/upload_profile_pic` | `upload_profile_pic` | `POST` | `login_required` | No description available |
| `/user/auto-schedule` | `user_auto_schedule` | `GET` | `login_required` | Renders the personal auto-scheduling page for users. |
| `/view-schedule-modal/<string:view_type>/<int:entity_id>` | `view_schedule_modal` | `GET` | `admin, superadmin` | Smart schedule viewer: uses uploaded layout template if available, else default grid. |
| `/view-timetable` | `view_timetable` | `GET` | `login_required` | No description available |
