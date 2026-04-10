# checklist2

Listado de rutas hardcodeadas detectadas en `app/`, `routers/`, `templates/`, `static/`, `utils/` y `tests/`.

## /
- app\main.py:79
- routers\dashboard.py:32
- routers\documents.py:1322
- routers\documents.py:1939
- tests\test_main_routes_coverage.py:10
- tests\test_main_routes_coverage.py:46
- utils\middleware.py:15

## /{doc_id}/download
- routers\documents.py:1669

## /{doc_id}/read
- routers\documents.py:1945

## /{user_id}
- routers\users.py:1024
- routers\users.py:907
- routers\users.py:978

## /{user_id}/edit
- routers\users.py:463
- routers\users.py:522

## /{user_id}/role
- routers\users.py:934

## /admin/logs
- routers\users.py:1065

## /admin/logs/export
- routers\users.py:399

## /api/v1/audit
- app\main.py:72

## /api/v1/audit/mappings/{first.id}/update
- tests\test_audit_routes.py:735
- tests\test_audit_routes.py:742

## /api/v1/audit/mappings/{mapping.id}/update
- tests\test_audit_routes.py:279

## /api/v1/audit/mappings/777777/delete
- tests\test_audit_routes.py:768

## /api/v1/audit/mappings/999999/update
- tests\test_audit_routes.py:728

## /api/v1/audit/mappings/create
- tests\test_audit_routes.py:155
- tests\test_audit_routes.py:219
- tests\test_audit_routes.py:553
- tests\test_audit_routes.py:597
- tests\test_audit_routes.py:659

## /api/v1/audit/view
- tests\test_audit_routes.py:111
- tests\test_audit_routes.py:173
- tests\test_audit_routes.py:59
- tests\test_audit_routes.py:88

## /api/v1/audit/view?control_q=A.5&status_filter=Implementado&responsible_filter={owner_a.id}
- tests\test_audit_routes.py:373

## /api/v1/audit/view?doc_page_size=10&doc_page=2&confirm_page_size=10&confirm_page=2
- tests\test_audit_routes.py:502

## /api/v1/audit/view?sort_by=control_iso&sort_dir=asc&page_size=10&page=1
- tests\test_audit_routes.py:430

## /api/v1/audit/view?sort_by=control_iso&sort_dir=desc&page_size=10&page=2
- tests\test_audit_routes.py:439

## /api/v1/audit/view?sort_by=invalid-sort&sort_dir=invalid-dir&page_size=999
- tests\test_audit_routes.py:850

## /api/v1/auth
- app\main.py:69

## /api/v1/auth/login
- tests\test_auth_and_dashboard_routes.py:144
- tests\test_auth_and_dashboard_routes.py:36
- tests\test_auth_and_dashboard_routes.py:72
- tests\test_auth_utils_coverage.py:155
- tests\test_auth_utils_coverage.py:166
- tests\test_auth_utils_coverage.py:189
- tests\test_auth_utils_coverage.py:36
- tests\test_main_routes_coverage.py:12
- tests\test_stats_utils.py:9
- tests\test_users_routes_coverage.py:142

## /api/v1/auth/logout
- tests\test_auth_and_dashboard_routes.py:69
- tests\test_users_additional_coverage.py:284

## /api/v1/auth/token
- tests\test_account_activation.py:33
- tests\test_account_activation.py:91
- tests\test_audit_routes.py:106
- tests\test_audit_routes.py:149
- tests\test_audit_routes.py:213
- tests\test_audit_routes.py:273
- tests\test_audit_routes.py:367
- tests\test_audit_routes.py:424
- tests\test_audit_routes.py:496
- tests\test_audit_routes.py:54
- tests\test_audit_routes.py:547
- tests\test_audit_routes.py:591
- tests\test_audit_routes.py:653
- tests\test_audit_routes.py:722
- tests\test_audit_routes.py:762
- tests\test_audit_routes.py:83
- tests\test_audit_routes.py:845
- tests\test_auth_and_dashboard_routes.py:25
- tests\test_auth_and_dashboard_routes.py:59
- tests\test_document_batch_upload.py:31
- tests\test_document_compliance_stats.py:170
- tests\test_document_compliance_stats.py:235
- tests\test_document_compliance_stats.py:277
- tests\test_document_compliance_stats.py:317
- tests\test_document_compliance_stats.py:67
- tests\test_document_read_certificate.py:107
- tests\test_document_read_certificate.py:150
- tests\test_document_read_certificate.py:222
- tests\test_document_read_certificate.py:44
- tests\test_document_upload_redirect.py:129
- tests\test_document_upload_redirect.py:175
- tests\test_document_upload_redirect.py:22
- tests\test_document_upload_redirect.py:267
- tests\test_document_upload_redirect.py:80
- tests\test_password_recovery.py:61
- tests\test_password_recovery.py:68
- tests\test_role_access.py:24
- tests\test_role_access.py:51
- tests\test_role_access.py:83
- tests\test_suggestions.py:125
- tests\test_suggestions.py:19
- tests\test_suggestions.py:78
- tests\test_users_additional_coverage.py:212
- tests\test_users_additional_coverage.py:26
- tests\test_users_additional_coverage.py:288
- tests\test_users_admin_routes.py:20
- tests\test_users_admin_routes.py:51
- tests\test_users_admin_routes.py:75
- tests\test_users_profile_routes.py:21
- tests\test_users_routes_coverage.py:29
- tests\test_users_routes_coverage.py:50
- tests\test_users_routes_coverage.py:76
- utils\auth.py:28
- utils\middleware.py:16

## /api/v1/dashboard
- app\main.py:70
- tests\test_auth_utils_coverage.py:34
- utils\middleware.py:30

## /api/v1/dashboard/
- tests\test_auth_and_dashboard_routes.py:135
- tests\test_dashboard_security.py:8
- tests\test_database_and_middleware.py:86

## /api/v1/documents
- app\main.py:71

## /api/v1/documents/{document.id}/download
- tests\test_document_read_certificate.py:118
- tests\test_document_read_certificate.py:159
- tests\test_document_read_certificate.py:176
- tests\test_document_read_certificate.py:190

## /api/v1/documents/{document.id}/read
- tests\test_document_read_certificate.py:112
- tests\test_document_read_certificate.py:62

## /api/v1/documents/{policy.id}/download
- tests\test_document_read_certificate.py:239
- tests\test_document_read_certificate.py:258
- tests\test_document_read_certificate.py:284

## /api/v1/documents/{policy.id}/read
- tests\test_document_read_certificate.py:227
- tests\test_document_read_certificate.py:271

## /api/v1/documents/reports/policies-reading-preview
- tests\test_document_compliance_stats.py:245
- tests\test_document_compliance_stats.py:282

## /api/v1/documents/reports/policies-reading-status
- tests\test_document_compliance_stats.py:175
- tests\test_document_compliance_stats.py:244
- tests\test_document_compliance_stats.py:322
- tests\test_document_compliance_stats.py:326

## /api/v1/documents/stats
- tests\test_document_compliance_stats.py:72

## /api/v1/documents/upload
- tests\test_document_upload_redirect.py:137
- tests\test_document_upload_redirect.py:184
- tests\test_document_upload_redirect.py:30
- tests\test_document_upload_redirect.py:89

## /api/v1/documents/upload/batch
- tests\test_document_batch_upload.py:57

## /api/v1/documents/view
- tests\test_dashboard_security.py:10
- tests\test_document_compliance_stats.py:240
- tests\test_document_upload_redirect.py:272
- tests\test_document_upload_redirect.py:44
- tests\test_document_upload_redirect.py:61

## /api/v1/media
- app\main.py:75

## /api/v1/media/media/profile_pics/avatar.png
- tests\test_media_and_user_utils.py:28
- tests\test_media_and_user_utils.py:39

## /api/v1/suggestions
- app\main.py:73

## /api/v1/suggestions/create
- tests\test_suggestions.py:25

## /api/v1/suggestions/view
- tests\test_suggestions.py:130
- tests\test_suggestions.py:31
- tests\test_suggestions.py:37
- tests\test_suggestions.py:83

## /api/v1/users
- app\main.py:74
- tests\__pycache__\test_role_access.cpython-313-pytest-9.0.2.pyc:19
- tests\__pycache__\test_role_access.cpython-314-pytest-9.0.2.pyc:18
- tests\test_auth_utils_coverage.py:124
- tests\test_dashboard_security.py:9
- tests\test_role_access.py:30
- tests\test_role_access.py:8
- tests\test_users_additional_coverage.py:38
- tests\test_users_routes_coverage.py:166
- tests\test_users_routes_coverage.py:379

## /api/v1/users/{admin.id}
- tests\test_users_additional_coverage.py:129
- tests\test_users_admin_routes.py:25

## /api/v1/users/{admin.id}/edit
- tests\test_users_additional_coverage.py:294
- tests\test_users_routes_coverage.py:328
- tests\test_users_routes_coverage.py:338

## /api/v1/users/{admin.id}/role
- tests\test_users_routes_coverage.py:552

## /api/v1/users/{other.id}/edit
- tests\test_role_access.py:87

## /api/v1/users/{target_user.id}
- tests\test_users_admin_routes.py:56

## /api/v1/users/{target_user.id}/edit
- tests\test_users_routes_coverage.py:292
- tests\test_users_routes_coverage.py:303
- tests\test_users_routes_coverage.py:367
- tests\test_users_routes_coverage.py:408
- tests\test_users_routes_coverage.py:420

## /api/v1/users/{target.id}
- tests\test_users_additional_coverage.py:113

## /api/v1/users/{user_two.id}
- tests\test_users_routes_coverage.py:592

## /api/v1/users/{user.id}/edit
- tests\test_role_access.py:55
- tests\test_users_additional_coverage.py:267

## /api/v1/users/9999
- tests\test_users_routes_coverage.py:615
- tests\test_users_routes_coverage.py:661

## /api/v1/users/9999/role
- tests\test_users_routes_coverage.py:637

## /api/v1/users/999999
- tests\test_users_additional_coverage.py:126

## /api/v1/users/999999/edit
- tests\test_users_additional_coverage.py:257
- tests\test_users_additional_coverage.py:261

## /api/v1/users/admin/logs
- tests\test_users_additional_coverage.py:241

## /api/v1/users/admin/logs?q=TOKEN&limit=10
- tests\test_users_routes_coverage.py:691

## /api/v1/users/admin/logs/export?limit=1
- tests\test_users_additional_coverage.py:54

## /api/v1/users/admin/logs/export?q=TOKEN&limit=10
- tests\test_users_admin_routes.py:87

## /api/v1/users/approved
- tests\test_users_additional_coverage.py:88
- tests\test_users_routes_coverage.py:189
- tests\test_users_routes_coverage.py:211

## /api/v1/users/approved/{new_email}
- tests\test_account_activation.py:49

## /api/v1/users/approved/dup@example.com
- tests\test_users_routes_coverage.py:233

## /api/v1/users/approved/registered@example.com
- tests\test_users_routes_coverage.py:262

## /api/v1/users/create
- tests\test_account_activation.py:56
- tests\test_users_additional_coverage.py:313
- tests\test_users_additional_coverage.py:72

## /api/v1/users/forgot-password
- tests\test_password_recovery.py:34
- tests\test_users_routes_coverage.py:96

## /api/v1/users/me
- tests\test_users_additional_coverage.py:219
- tests\test_users_profile_routes.py:112
- tests\test_users_profile_routes.py:41
- tests\test_users_profile_routes.py:61
- tests\test_users_profile_routes.py:84
- tests\test_users_routes_coverage.py:55

## /api/v1/users/me/password
- tests\test_users_profile_routes.py:139
- tests\test_users_routes_coverage.py:81

## /api/v1/users/resend-verification
- tests\test_users_routes_coverage.py:461
- tests\test_users_routes_coverage.py:487
- tests\test_users_routes_coverage.py:514
- tests\test_users_routes_coverage.py:527
- utils\middleware.py:18

## /api/v1/users/reset-password/{token}
- tests\test_password_recovery.py:46
- tests\test_password_recovery.py:53

## /api/v1/users/reset-password/invalid-token
- tests\test_users_routes_coverage.py:107
- tests\test_users_routes_coverage.py:113
- tests\test_users_routes_coverage.py:120
- tests\test_users_routes_coverage.py:126
- tests\test_users_routes_coverage.py:136

## /api/v1/users/reset-password/token123
- tests\test_users_additional_coverage.py:230

## /api/v1/users/verify
- utils\middleware.py:17

## /api/v1/users/verify/{token}
- tests\test_account_activation.py:82
- tests\test_users_routes_coverage.py:442
- tests\test_users_routes_coverage.py:452

## /approved
- routers\users.py:643

## /approved/{approved_email}
- routers\users.py:669

## /create
- routers\suggestions.py:80
- routers\users.py:720

## /favicon.ico
- app\main.py:90
- tests\test_main_routes_coverage.py:14

## /forgot-password
- app\main.py:104
- routers\users.py:195
- routers\users.py:218
- tests\test_main_routes_coverage.py:18

## /login
- routers\auth.py:29
- tests\test_database_and_middleware.py:29
- tests\test_database_and_middleware.py:96
- tests\test_users_additional_coverage.py:134

## /logout
- routers\auth.py:128

## /mappings/{mapping_id}/delete
- routers\audit.py:417

## /mappings/{mapping_id}/update
- routers\audit.py:258

## /mappings/create
- routers\audit.py:114

## /me
- routers\users.py:72
- routers\users.py:89

## /me/password
- routers\users.py:163

## /media
- app\main.py:50
- utils\middleware.py:26

## /media/profile_pics/{filename}
- routers\media.py:8

## /reports/policies-reading-preview
- routers\documents.py:1169

## /reports/policies-reading-status
- routers\documents.py:1277

## /resend-verification
- routers\users.py:845
- routers\users.py:866

## /reset-password
- app\main.py:122
- tests\test_main_routes_coverage.py:25

## /reset-password/{token}
- routers\users.py:261
- routers\users.py:285

## /sgsi
- app\main.py:41

## /static
- app\main.py:48
- utils\middleware.py:26

## /static/css/dashboard.css
- tests\test_database_and_middleware.py:73
- tests\test_database_and_middleware.py:76

## /stats
- routers\documents.py:1385

## /token
- routers\auth.py:54

## /unread-report
- tests\test_document_compliance_stats.py:247

## /upload
- routers\documents.py:1463

## /upload/batch
- routers\documents.py:1579

## /verify/{token}
- routers\users.py:805

## /view
- routers\audit.py:475
- routers\documents.py:1193
- routers\suggestions.py:21

## /x
- tests\test_users_additional_coverage.py:185

## /�
- routers\__pycache__\audit.cpython-314.pyc:154
- routers\__pycache__\audit.cpython-314.pyc:75

## /���4�v5;L
- static\images\bg-login.jpg:236

