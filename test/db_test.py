import sqlite3
from src.backend.db import connect, create_schema, create_run, create_query, create_candidate, list_run_candidates

def main() -> None:
    try:
        #init
        path = "src/backend/test/dummy.sqlite"
        db = connect(path)
        create_schema(db)

        #create dummy entries
        run_id = create_run(db, "dummy")
        yt_id = create_query(db, run_id, "None", 200, "dummy", 0, "youtube")
        red_id = create_query(db, run_id, "None", 200, "dummy", 0, "reddit")
        platfrom_yt = f"yt{run_id}"
        platfrom_red = f"red{run_id}"
        link_yt = f"http{run_id}"
        link_red = f"httpt{run_id}"
        create_candidate(db, run_id, yt_id, "youtube", platfrom_yt, "None", "None", link_yt, "None", "None", "None")
        create_candidate(db, run_id, red_id, "reddit", platfrom_red, "None", "None", link_red, "None", "None", "None")

        #read joined candidate rows
        raws = list_run_candidates(db, run_id)
        print("check:")
        for raw in raws:
            print(dict(raw))

        assert len(raws) == 2, "row count error"

        #expected fields check
        query_source = {raw["query_source"] for raw in raws}
        candidate_source = {raw["candidate_source"] for raw in raws}
        candidate_link = {raw["candidate_link"] for raw in raws}

        assert raws[0]["run_target"] == "dummy", "run target error"
        assert raws[0]["query_text"] == "dummy", "query text error"
        assert raws[0]["candidate_title"] == "None", "candidate title error"
        assert candidate_link == {f"http{run_id}", f"httpt{run_id}"}, "candidate link error"
        assert candidate_source == {"youtube", "reddit"}, "candidate source error"
        assert query_source == {"youtube", "reddit"}, "query source error"

    except sqlite3.IntegrityError as e:
        print(f"{e}")
    
    try:
        create_candidate(db, run_id, yt_id, "youtube", platfrom_yt, "None", "None", link_yt, "None", "None", "None")
        assert False, "assert error"
    except sqlite3.IntegrityError:
        print("pass")

if __name__ == "__main__":
    main() 