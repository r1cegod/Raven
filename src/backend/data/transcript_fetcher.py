from pathlib import Path
from typing import Any
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import YouTubeTranscriptApiException
from src.backend.db import transcript_log, get_title


api = YouTubeTranscriptApi()

def format_timestamp(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h:02}:{m:02}:{s:02}"
    return f"{m:02}:{s:02}"


def transcript_fetch(
        db: Any,
        run_id: int, 
        query_id: int, 
        video_id: str, 
        target_lang: str = "en"
    ):
    transcript = None
    try:
        title_pack = get_title(db, run_id, video_id)
        title = title_pack["title"]
        description = title_pack["description"]
        run_id = str(run_id)
        query_id = str(query_id)

        #initialize the folder
        defaut_path = Path("/mnt/d/ANHDUC/ADUC_vault/ADUC/sources/transcripts")
        folder = defaut_path / run_id / query_id 
        folder.mkdir(parents=True, exist_ok=True)

        #fetch transcript
        transcripts = api.list(video_id)


        for trans in transcripts:
            if trans.language_code == target_lang:
                transcript = trans.fetch()
                break

        if not transcript:
            transcript_log(db, run_id, query_id, video_id, failure_type="no transcript", failure_reason="can't pull any transcript")

        #write the md file
        else:
            segments = transcript.to_raw_data()
            url = f"https://www.youtube.com/watch?v={video_id}"

            path = folder / f"{video_id}.md"

            with open(path, "w", encoding="utf-8") as f:
                f.write("## Metadata\n")
                f.write(f"- title: {title}\n")
                f.write(f"- description: {description}\n")
                f.write(f"- video_id: {video_id}\n")
                f.write(f"- url: {url}\n")
                f.write("\n## Transcript\n\n")

                for segment in segments:
                    timestamp = format_timestamp(segment["start"])
                    text = segment["text"].replace("\n", " ")
                    f.write(f"[{timestamp}] {text}\n\n")    

            transcript_log(db, run_id, query_id, video_id, failure_type="", failure_reason="", status=True)

    except YouTubeTranscriptApiException as e:
        transcript_log(db, run_id, query_id, video_id, failure_type=type(e).__name__, failure_reason=str(e))