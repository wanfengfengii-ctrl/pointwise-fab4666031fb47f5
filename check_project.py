"""Run this project's full unittest suite and the replacement drill from the repository root."""
import sys
import unittest


def _run_suite() -> bool:
    suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
    if suite.countTestCases():
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        print('No tests discovered in tests/', file=sys.stderr)
        result = unittest.TestResult()
    for status, failed_cases in (
        ('FAIL', (test for test, _ in result.failures)),
        ('ERROR', (test for test, _ in result.errors)),
        ('UNEXPECTED_SUCCESS', result.unexpectedSuccesses),
    ):
        for test in failed_cases:
            print(f'{status} {test.id()}')
    successful = result.testsRun > 0 and result.wasSuccessful()
    print(f'TEST SUMMARY total={result.testsRun} failures={len(result.failures)} '
          f'errors={len(result.errors)} skipped={len(result.skipped)} '
          f'expected_failures={len(result.expectedFailures)} '
          f'unexpected_successes={len(result.unexpectedSuccesses)} '
          f'result={"PASS" if successful else "FAIL"}')
    return successful


def _run_replacement_drill() -> bool:
    from samples.replacement_drill import run_all
    try:
        run_all()
    except AssertionError as error:
        print(f'REPLACEMENT DRILL FAIL {error}', file=sys.stderr)
        return False
    print('REPLACEMENT DRILL PASS')
    return True


def main():
    return 0 if (_run_suite() and _run_replacement_drill()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
