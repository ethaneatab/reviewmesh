# Before q09: process whatever the queue hands us, in the order it hands it over.
# @learn:before-order
def handle(self, body):
    rid, seq = body["record_id"], int(body["seq"])
    stage = self.process(self, body)
    db.execute("UPDATE workflow_state SET last_seq = %s WHERE record_id = %s", (seq, rid))
    return stage
# @learn:end before-order
