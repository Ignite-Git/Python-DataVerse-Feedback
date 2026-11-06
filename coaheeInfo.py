from datetime import datetime
import re

from dataverse_connection import get_dataverse_client
from PowerPlatform.Dataverse.models import col


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def fetch_all_pages(query):
    """
    Fetch all pages returned by a Dataverse query.
    """
    results = []

    for page in query.page_size(500).execute_pages():
        results.extend(page)

    return results


def chunks(items, size=100):
    """
    Split a list into smaller batches.
    """
    for i in range(0, len(items), size):
        yield items[i:i + size]


def normalize_guid(value):
    """
    Normalize GUIDs so that comparisons are consistent.
    """
    if not value:
        return None

    return str(value).strip().strip("{}").lower()


def normalize_person_id(value):
    """
    Normalize Person IDs for consistent comparisons.
    """
    if not value:
        return None

    return str(value).strip().upper()


def extractCoachId(session_id: str) -> str:
    """
    Extract the coach number from a session ID.

    Example:
        PER02/09102026/S1 -> PER 000002
        PER22/09102026/S1 -> PER 000022
    """

    prefix = session_id.split("/")[0].strip().upper()

    match = re.fullmatch(r"PER\s*0*(\d+)", prefix)

    if not match:
        raise ValueError(f"Invalid coach ID in session ID: {session_id}")

    coach_number = int(match.group(1))

    return f"PER {coach_number:06d}"


def compareSessionDate(old_sessionid: str, new_sessionid: str) -> str:
    """
    Return the session ID with the earliest date.

    Session format:
        PER02/09102026/S1

    Date format:
        DDMMYYYY
    """

    old_date = datetime.datetime.strptime(
        old_sessionid.split("/")[1],
        "%d%m%Y"
    )

    new_date = datetime.datetime.strptime(
        new_sessionid.split("/")[1],
        "%d%m%Y"
    )

    return new_sessionid if new_date < old_date else old_sessionid


# ---------------------------------------------------------
# STEP 1: GET SESSIONS WITHOUT FEEDBACK AND THEIR COACHEES
# ---------------------------------------------------------


def singleCoachees() -> dict:

    session_info = {}

    try:
        with get_dataverse_client() as client:

            # 1. Get sessions without feedback
            sessions = client.records.list(
                "cref0_sessiontable",
                select=[
                    "cref0_sessiontableid",
                    "cref0_sessionid"
                ],
                filter=(
                    "cref0_userfeedback eq null "
                    "or cref0_userfeedback eq ''"
                )
            )

            # 2. Index sessions using their Dataverse GUID
            session_lookup = {}

            for session in sessions:

                data = session.data

                session_guid = normalize_guid(
                    data.get("cref0_sessiontableid")
                )

                session_id = data.get("cref0_sessionid")

                if not session_guid or not session_id:
                    continue

                session_lookup[session_guid] = {
                    "sessionid": session_id,
                    "sessiontableid": session_guid,
                    "coacheeids": []
                }

            if not session_lookup:
                return session_info

            # 3. Get the session GUIDs
            session_guids = list(session_lookup.keys())

            # 4. Retrieve Coach Logs associated with these sessions
            for batch in chunks(session_guids, 100):

                filters = [
                    f"_cref0_logsessionid_value eq {session_guid}"
                    for session_guid in batch
                ]

                odata_filter = " or ".join(
                    f"({condition})" for condition in filters
                )

                coach_logs = client.records.list(
                    "cref0_coachlogtable",
                    select=[
                        "cref0_coacheeids",
                        "_cref0_logsessionid_value"
                    ],
                    filter=odata_filter
                )

                # 5. Process Coach Logs
                for log in coach_logs:

                    data = log.data

                    session_guid = normalize_guid(
                        data.get("_cref0_logsessionid_value")
                    )

                    if session_guid not in session_lookup:
                        continue

                    raw_coachees = data.get("cref0_coacheeids")

                    if not raw_coachees:
                        continue

                    # Support single or semicolon-separated IDs
                    coachee_ids = [
                        normalize_person_id(person_id)
                        for person_id in str(raw_coachees).split(";")
                        if person_id.strip()
                    ]

                    existing_ids = set(
                        session_lookup[session_guid]["coacheeids"]
                    )

                    # Add unique coachee IDs
                    for person_id in coachee_ids:

                        if person_id and person_id not in existing_ids:

                            session_lookup[session_guid]["coacheeids"].append(
                                person_id
                            )

                            existing_ids.add(person_id)

            # 6. Return only sessions with coachees
            session_info = {
                session_guid: details
                for session_guid, details in session_lookup.items()
                if details["coacheeids"]
            }

    except Exception as e:
        print(f"Error in singleCoachees(): {e}")

    return session_info



# ---------------------------------------------------------
# STEP 2: CHECK MASTER TABLE, COACHEE TABLE AND REVIEWS
# ---------------------------------------------------------


from PowerPlatform.Dataverse.models import col


def checkInReviews(session_info: dict) -> dict:

    userDetails = {}
    sessionDetails = {}

    try:
        with get_dataverse_client() as client:

            # --------------------------------------------------
            # 1. Collect unique PersonIDs from session_info
            # --------------------------------------------------

            person_ids = list({
                normalize_person_id(person_id)
                for session in session_info.values()
                for person_id in session.get("coacheeids", [])
                if normalize_person_id(person_id)
            })

            if not person_ids:
                return {
                    "userDetails": [],
                    "sessionDetails": {}
                }

            # --------------------------------------------------
            # 2. Retrieve matching Master Table records
            #    Fullname and email come from this table
            # --------------------------------------------------

            master_by_person = {}

            for batch in chunks(person_ids, 100):

                pages = (
                    client.query.builder("cref0_mastertable")
                    .select(
                        "cref0_mastertableid",
                        "cref0_personid",
                        "cref0_fullname",
                        "cref0_email"
                    )
                    .where(col("cref0_personid").in_(batch))
                    .page_size(500)
                    .execute_pages()
                )

                for page in pages:

                    for record in page:

                        data = record.data

                        person_id = normalize_person_id(
                            data.get("cref0_personid")
                        )

                        if not person_id:
                            continue

                        master_guid = normalize_guid(
                            data.get("cref0_mastertableid")
                        )

                        master_by_person[person_id] = {
                            "master_guid": master_guid,
                            "fullname": data.get("cref0_fullname"),
                            "email": data.get("cref0_email")
                        }

            if not master_by_person:
                return {
                    "userDetails": [],
                    "sessionDetails": {}
                }

            # --------------------------------------------------
            # 3. Retrieve Coachee Table records
            #    Match each Coachee to its Master Table record
            # --------------------------------------------------

            master_guids = list({
                details["master_guid"]
                for details in master_by_person.values()
                if details["master_guid"]
            })

            coachee_by_master = {}

            for batch in chunks(master_guids, 100):

                filters = [
                    f"_cref0_coacheeid_value eq {master_guid}"
                    for master_guid in batch
                ]

                odata_filter = " or ".join(
                    f"({condition})" for condition in filters
                )

                coachee_records = client.records.list(
                    "cref0_coacheetable",
                    select=[
                        "cref0_coacheetableid",
                        "_cref0_coacheeid_value"
                    ],
                    filter=odata_filter
                )

                for record in coachee_records:

                    data = record.data

                    master_guid = normalize_guid(
                        data.get("_cref0_coacheeid_value")
                    )

                    coachee_guid = normalize_guid(
                        data.get("cref0_coacheetableid")
                    )

                    if master_guid and coachee_guid:

                        coachee_by_master[master_guid] = coachee_guid

            if not coachee_by_master:
                return {
                    "userDetails": [],
                    "sessionDetails": {}
                }

            # --------------------------------------------------
            # 4. Retrieve reviews for the relevant coachees
            # --------------------------------------------------

            coachee_guids = list(set(coachee_by_master.values()))

            review_pairs = set()

            for batch in chunks(coachee_guids, 100):

                filters = [
                    f"_cref0_revcoacheeid_value eq {coachee_guid}"
                    for coachee_guid in batch
                ]

                odata_filter = " or ".join(
                    f"({condition})" for condition in filters
                )

                review_records = client.records.list(
                    "cref0_coachreviewtable",
                    select=[
                        "_cref0_revcoacheeid_value",
                        "_cref0_crevsessionid_value"
                    ],
                    filter=odata_filter
                )

                for record in review_records:

                    data = record.data

                    coachee_guid = normalize_guid(
                        data.get("_cref0_revcoacheeid_value")
                    )

                    session_guid = normalize_guid(
                        data.get("_cref0_crevsessionid_value")
                    )

                    if coachee_guid and session_guid:
                        review_pairs.add(
                            (coachee_guid, session_guid)
                        )

            
            # --------------------------------------------------
            # 5. Check outstanding feedback for each session
            # --------------------------------------------------

            coach_coachee_ids = {}

            for session_guid, session in session_info.items():

                session_guid = normalize_guid(session_guid)
                session_id = session.get("sessionid")

                if not session_guid or not session_id:
                    continue

                coach_id = extractCoachId(session_id)

                if not coach_id:
                    continue

                # Group sessions under their respective coaches
                sessionDetails.setdefault(coach_id, {
                    "coachees": []
                })

                coach_coachee_ids.setdefault(coach_id, set())

                for person_id in session.get("coacheeids", []):

                    person_id = normalize_person_id(person_id)

                    if not person_id:
                        continue

                    master = master_by_person.get(person_id)

                    if not master:
                        continue

                    master_guid = master.get("master_guid")

                    if not master_guid:
                        continue

                    coachee_guid = coachee_by_master.get(master_guid)

                    if not coachee_guid:
                        continue

                    # Check whether feedback already exists
                    if (coachee_guid, session_guid) in review_pairs:
                        continue

                    # Coachee still needs to submit feedback
                    fullname = master.get("fullname")

                    # Add each coachee only once per coach
                    if person_id not in coach_coachee_ids[coach_id]:

                        if fullname:
                            sessionDetails[coach_id]["coachees"].append({
                                "personid": person_id,
                                "fullname": fullname.strip()
                            })

                        coach_coachee_ids[coach_id].add(person_id)

                    # --------------------------------------------------
                    # 6. Keep earliest outstanding session per PersonID
                    # --------------------------------------------------

                    new_user_details = {
                        "personid": person_id,
                        "fullname": fullname,
                        "email": master.get("email"),
                        "sessionid": session_id,
                        "coachid": coach_id
                    }

                    existing = userDetails.get(person_id)

                    if not existing:

                        userDetails[person_id] = new_user_details

                    else:

                        try:
                            new_date = datetime.strptime(
                                session_id.split("/")[1], "%d%m%Y"
                            )

                            existing_date = datetime.strptime(
                                existing["sessionid"].split("/")[1], "%d%m%Y"
                            )

                            if new_date < existing_date:
                                userDetails[person_id] = new_user_details

                        except (ValueError, IndexError):
                            pass


            # --------------------------------------------------
            # 7. Remove coaches without outstanding coachees
            # --------------------------------------------------

            sessionDetails = [
                {
                    "coachid": coach_id,
                    "coachees": details["coachees"]
                }
                for coach_id, details in sessionDetails.items()
                if details["coachees"]
            ]


            # --------------------------------------------------
            # 8. Return results
            # --------------------------------------------------

            return {
                "userDetails": list(userDetails.values()),
                "sessionDetails": sessionDetails
            }

    except Exception as e:

        print(f"Error in checkInReviews(): {e}")

        return {
            "userDetails": [],
            "sessionDetails": {}
        }
