from pathlib import Path


def test_txt_examples_exist() -> None:
    assert Path("samples/master-services-agreement.txt").exists()
    assert Path("samples/supplier-agreement.txt").exists()
