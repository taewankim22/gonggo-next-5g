from ui_components import required_progress, submission_url


def test_required_progress_excludes_later_unknown_and_optional_documents():
    rows = [
        dict(category='필수', stage='지원 단계', readiness='준비 완료', later=False),
        dict(category='필수', stage='지원 단계', readiness='아직 확인하지 않음', later=False),
        dict(category='필수', stage='선발 후·활동 중', readiness='준비 완료', later=True),
        dict(category='필수', stage='시점 확인 필요', readiness='준비 완료', later=False),
        dict(category='선택', stage='지원 단계', readiness='준비 완료', later=False),
    ]
    assert required_progress(rows) == (1, 2)
    assert required_progress([]) == (0, 0)


def test_submission_links_only_use_explicit_web_urls():
    assert submission_url('학교 홈페이지에서 신청') is None
    assert submission_url('javascript:alert(1)') is None
    assert submission_url('온라인 접수 (https://example.org/apply).') == 'https://example.org/apply'
