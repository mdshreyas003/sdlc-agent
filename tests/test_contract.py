from whycode.contract import Anchor, Answer


def test_refusal_round_trips_through_json():
    answer = Answer(anchor=Anchor(kind="setting", id="sql.defaults.use_declarative_schema_changer"),
                    refused=True, confidence="Low")

    assert Answer.model_validate_json(answer.model_dump_json()) == answer
