from app.modules.hr.scheduler import MailFetchScanner, ResumeFolderScanner


def test_legacy_hr_scanners_implement_scheduler_generator_contract() -> None:
    resume_scanner = ResumeFolderScanner()
    mail_scanner = MailFetchScanner()

    assert resume_scanner.schedule.interval_seconds == 30
    assert mail_scanner.schedule.interval_seconds == 600
    assert callable(resume_scanner.find_due)
    assert callable(resume_scanner.execute_one)
    assert callable(mail_scanner.find_due)
    assert callable(mail_scanner.execute_one)
