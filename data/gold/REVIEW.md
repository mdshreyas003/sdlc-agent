# Gold review

For each question: is it a real, non-trivial *why*? Do the facts follow from the quotes? Tell Claude the ids to fix or drop; ids you approve get `human_verified=true`.


## Q001 · tier B · KIP-98 · test

**Why were the idempotent producer and the transactional API designed and proposed together as one feature, rather than shipping idempotent delivery on its own first?**

- fact: The two were originally drafted as separate proposals but this was confusing because of interdependencies between the concepts
- fact: They share underlying mechanics such as the message format changes and the InitPidRequest
- fact: Idempotence and transactions are seen as the two essential ingredients of the exactly-once story
- evidence: <https://kafka-dev.slack.com/archives/KIP98/p1481050861000024>
  > We started with separate KIPs but it made it very confusing to read since there were interdependencies between the concepts.
- evidence: <https://kafka-dev.slack.com/archives/KIP98/p1481219203000031>
  > some of the underlying mechanics are shared, such as the message format changes and the InitPidRequest.
- note: Two senders (Sriram, Jason) answer the same objection from a reviewer who wanted idempotence without transactions.

## Q002 · tier B · KIP-98 · test

**Why does the broker not reject transactional produce requests until every broker in the cluster is on the new message format, and rely on documentation instead?**

- fact: A cluster should not be advertised as transaction ready until all brokers are on the new message format; this is handled by organizational policy
- fact: Engineering solutions such as brokers registering as transaction ready are left out of the first version and may be future work
- fact: The impact is documented in the upgrade doc, which the reviewer accepted for the first version
- evidence: <https://kafka-dev.slack.com/archives/KIP98/p1485393356000105>
  > I think the non-engineering solution is reasonable, and as such would prefer to not include engineering solutions in V1. It could be future work if necessary.
- evidence: <https://kafka-dev.slack.com/archives/KIP98/p1485711562000111>
  > Yes, in the first version, we can just document the impact in the upgrade doc.
- note: Decision proposed by the author in one message and confirmed by the reviewer (Jun) in a later one.

## Q003 · tier A · KIP-98 · test

**Why can't a producer id simply be reused once a producer goes away, and why not hand out and expire ids through ZooKeeper?**

- fact: A PID expires per partition when it falls off the log, so the log stays the source of truth for PID sequences
- fact: Safely reusing a PID needs global coordination to be sure it expired on all partitions
- fact: They did not want any per-producer state stored in ZooKeeper
- evidence: <https://kafka-dev.slack.com/archives/KIP98/p1481066874000026>
  > The problem then is that it's difficult to tell when it is safe to reuse a PID without some mechanism for global coordination.
- evidence: <https://kafka-dev.slack.com/archives/KIP98/p1481066874000026>
  > This could be done through Zk perhaps, but we didn't really want to have any per-producer state stored there.
- note: Single message from Jason answering Jay's question about 4-byte PID size and expiry.

## Q004 · tier B · KIP-98 · test

**Why does the consumer skip the per-record CRC check with the new message format, and why is the CRC no longer stored per record?**

- fact: The record-level CRC moved to the batch header
- fact: Computing a per-record CRC on the fly for the consumer API degrades performance and is unnecessary given the batch CRC
- fact: The per-record CRC is only still computed to retain backwards compatibility with the client API, so the performance results depend on disabling it
- evidence: <https://kafka-dev.slack.com/archives/KIP98/p1490204981000197>
  > The consumer record API still allows retrieval of CRC per record, and in this case we compute the CRC on the fly. This degrades performance
- evidence: <https://kafka-dev.slack.com/archives/KIP98/p1490767822000200>
  > this depends on disabling the record-level CRC, which we currently compute only to retain backwards compatibility with the client API
- note: A Jira issue (Apurva) plus the later format-update mail (Jason) jointly explain the reason.

## Q005 · tier T · KIP-98 · dev

**Was the Connect worker's default header converter handling fixed because of the record format changes introduced for transactions?**

- fact: Not established: the commit and the mail do not reference each other
- evidence: <https://github.com/apache/kafka/commit/d9369de8f2c6435843fb7577d313bb24e3b09cba>
  > The `Plugins.newHeaderConverter` methods were always returning null if the `header.converter` configuration value was not specified
- evidence: <https://kafka-dev.slack.com/archives/KIP98/p1490767822000200>
  > This patch also included the message format changes for KIP-101 and KIP-82.
- note: Checked by grep: the commit (KAFKA-6728, AK 1.1, header.converter) shares no Jira key, PR number or url with the mail (KIP-101, KIP-82, KAFKA-4935); both involve record headers but neither names the other.

## Q006 · tier N · KIP-98 · dev

**Why does the transaction state topic default to 50 partitions instead of a smaller number?**

- fact: No reason for the 50-partition default is given anywhere in the corpus
- note: Grepped the corpus for num.partitions, transaction.state.log, __transaction_state and 50 partitions: no artifact explains the default, and the answer key only lists it.

## Q007 · tier B · KIP-129 · test

**Why does Streams exactly-once mode use one producer per task, given that an instance with many partitions ends up with a lot of producers?**

- fact: Producer per task was kept as a clean first design (EoS 1.0) because the performance concerns were hard to quantify up front
- fact: Concerns can be mitigated: PartitionGrouper can reduce task count, a producer pool could share resources
- fact: A move to producer per thread can be done incrementally later
- evidence: <https://kafka-dev.slack.com/archives/KIP129/p1489615740000010>
  > The raised concerns are all valid, but hard to quantify at the moment.
- evidence: <https://kafka-dev.slack.com/archives/KIP129/p1488855314000004>
  > it is possible to specify a custom PartitionGrouper that assigns multiple partitions to a single task.
- evidence: <https://kafka-dev.slack.com/archives/KIP129/p1488855314000004>
  > a "producer per thread" design would be way more complex
- note: Reason split across the first reply and the later proposal to ship as is.

## Q008 · tier A · KIP-129 · test

**Why does Streams not let downstream sub-topologies read uncommitted data from intermediate topics in exactly-once mode?**

- fact: Reading uncommitted data optimistically would require cascading abort of transactions on failure
- fact: That is an advanced design left for a separate KIP
- evidence: <https://kafka-dev.slack.com/archives/KIP129/p1488855314000004>
  > In case of failure, a cascading abort of transactions would be required. This change will need another KIP.
- note: Single message states the reason.

## Q009 · tier B · KIP-129 · test

**Why is it acceptable that an aborted transaction in exactly-once mode wipes the local state store and restores it from the changelog?**

- fact: Same strategy as before EoS (0.10.2), already run in production
- fact: Such failures are expected to be rare: transient broker/network errors that producer retries mask
- fact: Restore is needed because non-EoS reuses the store as-is but EoS needs a clean store; faster restore improvements are treated as later add-ons
- evidence: <https://kafka-dev.slack.com/archives/KIP129/p1490139796000013>
  > It's the same strategy as used in 0.10.2 and it runs in production in many companies already.
- evidence: <https://kafka-dev.slack.com/archives/KIP129/p1490381792000019>
  > For EoS, we need to get a "clean" store on retry to guarantee exactly-once.
- evidence: <https://kafka-dev.slack.com/archives/KIP129/p1490381792000019>
  > We can assume, that brokers do fail rarely.
- note: Combines Matthias's first answer with his later detailed failure analysis.

## Q010 · tier A · KIP-129 · test

**Why does exactly-once mode in Streams force acks=all on its producers rather than leaving the default?**

- fact: Transactions (KIP-98) require acks=-1, otherwise a config exception is thrown
- fact: acks=1 could lose acked data on leader change
- evidence: <https://kafka-dev.slack.com/archives/KIP129/p1488937525000007>
  > For transactions, it's further required that acks=-1 to avoid a config exception.
- note: Rationale from KIP-98 constraint stated in one reply; the data-loss worry came from the question.

## Q011 · tier T · KIP-129 · test

**Was the transactionInFlight flag in StreamTask, which commits an open transaction on suspend, added because of the discussion on how failures and aborted transactions are handled?**

- fact: Not established: no artifact links the commit to that discussion
- evidence: <https://github.com/apache/kafka/commit/39c1e6259c8ff547c3f7c5165b43c88f9f3ea158>
  > need to make sure to commit txn for suspend case
- evidence: <https://kafka-dev.slack.com/archives/KIP129/p1490381792000019>
  > For non-EoS, as we guarantee at-least-once processing, the state store is just used as-is on a retry.
- note: Commit (KAFKA-5361, #3193) and mail (2017-03-24) share no Jira key, PR number or URL; grep checked.

## Q012 · tier B · KIP-405 · dev

**Why did tiered storage split the remote-storage plugin into a segment-data manager and a separate remote log metadata manager, instead of having the broker discover remote segments by listing the remote store?**

- fact: Listing an object store such as S3 for metadata is costly (LIST request pricing at many partitions)
- fact: Relying on remote storage for metadata requires strong consistency, which S3 listing does not give
- fact: Metadata was therefore moved to a separate strongly consistent store (default: an internal topic), leaving segment storage free to be eventually consistent
- evidence: <https://kafka-dev.slack.com/archives/KIP405/p1575499997000071>
  > (a) Cost: S3 list object requests cost $0.005 per 1000 requests. If you have 100,000 partitions and want to pull the metadata for each partition at the rate of 1/sec.
- evidence: <https://kafka-dev.slack.com/archives/KIP405/p1581503803000078>
  > But one of the problems of relying on the remote storage to maintain metadata is that tiered-storage needs to be strongly consistent, with an impact not only on the metadata(e.g. LIST in S3) but also on the segment data(e.g. GET after a DELETE in S3).
- note: Reviewer objection (cost/consistency of S3 LIST) in one message, design change confirming it as the reason in another.

## Q013 · tier B · KIP-405 · dev

**Why are compacted topics not supported with tiered storage in the first version?**

- fact: Compacted topics are generally small and do not use much disk, so they are low priority
- fact: Remote segment files are treated as read-only, while compaction must rewrite segments periodically
- fact: Compacting on remote storage would make things much more complicated
- evidence: <https://kafka-dev.slack.com/archives/KIP405/p1571994301000042>
  > Generally, compact topics do not consume large disk unlike non-compact topics do. So, this is not a high priority for now.
- evidence: <https://kafka-dev.slack.com/archives/KIP405/p1572292255000044>
  > The segment files in remote storage are considered as read-only. They are not going to be changed until deleted after expire.
- note: Two authors give complementary reasons (low disk benefit; immutability of remote segments).

## Q014 · tier A · KIP-405 · test

**Why does the broker itself upload closed segments to remote storage, rather than exposing an API that lets an external tool or cron job register where it copied a segment?**

- fact: The broker has the latest topic information, such as whether it is still the leader and whether a segment is closed
- fact: Users can manage everything in one place, the Kafka topic configuration
- evidence: <https://kafka-dev.slack.com/archives/KIP405/p1572291697000043>
  > Kafka broker has the latest topic information, such as if the broker is still the leader, if a segment file is already closed (high watermark has been moved to the next segment)
- evidence: <https://kafka-dev.slack.com/archives/KIP405/p1572291697000043>
  > For the users, it's also easier to manage everything at one place: the Kafka topic configuration.
- note: Single message answering an alternative proposed by a reviewer.

## Q015 · tier A · KIP-405 · dev

**Why does the remote log index use a coarser index interval and one index file spanning many remote segments, instead of one index file per segment like the local log?**

- fact: Segments are rolled very fast to ship data early, producing many small segments
- fact: One index file per remote segment could hit OS limits on open or mmapped files
- evidence: <https://kafka-dev.slack.com/archives/KIP405/p1573087763000054>
  > If we maintain one remote index file for each remote segment, we can easily hit some OS limitations, like the maximum # of open files or the maximum # of mmapped files.
- evidence: <https://kafka-dev.slack.com/archives/KIP405/p1573087763000054>
  > Because only inactive segments can be shipped to remote storage, to be able to ship log data as soon as possible, we will roll log segment very fast (e.g. every half hour).
- note: Full rationale in one message.

## Q016 · tier T · KIP-405 · test

**Was the change that keeps one producer state snapshot file per log segment (and deletes it with the segment) made because of the discussion about pulling remote segment metadata with S3 LIST calls?**

- fact: Not established: no artifact links the snapshot change to the remote metadata listing discussion
- evidence: <https://issues.apache.org/jira/browse/KAFKA-9393>
  > One possible solution is to maintain a producer state snapshot aligned to the log segment, and simply delete it whenever we delete a segment.
- evidence: <https://kafka-dev.slack.com/archives/KIP405/p1577448743000077>
  > If we want to keep the pull-based approach, we can try to reduce this number in several ways: doing listings less frequently
- note: Mail 2019-12-27 and Jira KAFKA-9393 (2020-01-09) are close in time. Grep: the mail mentions neither KAFKA-9393 nor PR 7929 nor the snapshot change; the issue/PR/commit never mention the mail, tiered storage or LIST. Issue is about DeleteRecords lock contention.

## Q017 · tier N · KIP-405 · test

**Why does the broker upload segments to remote storage as-is, without re-compressing or otherwise transforming them first?**

- note: Grepped corpus for compress/compression/ZSTD: no hits; answer key does not state it either.

## Q018 · tier B · KIP-447 · dev

**Why does the offset fetch for a read-committed consumer return a retriable pending-transaction error that makes the client back off and retry, instead of having the broker hold the request until the pending transactional offsets clear?**

- fact: Holding the request would tie up a broker handler thread or need a purgatory, which is more complicated
- fact: Retrying is less likely to violate the request timeout
- fact: Reusing the retry approach avoids another purgatory instance and the back-off cost at startup is small
- evidence: <https://kafka-dev.slack.com/archives/KIP447/p1561485061000007>
  > One advantage of retry against on-hold is that it will not tie-up a handler thread (of course the latter could do the same but that involves using a purgatory which is more complicated), and also it is less likely to violate request timeout.
- evidence: <https://kafka-dev.slack.com/archives/KIP447/p1561499832000009>
  > That sounds fair to me, also we are avoiding usage of another purgatory instance.
- note: Guozhang gives the rationale, Boyang confirms and adds the purgatory/back-off point.

## Q019 · tier B · KIP-447 · test

**Why does the transaction coordinator not keep its own copy of the consumer group's partition assignment (nor get colocated with the group coordinator), leaving fencing of stale offset commits to the group coordinator?**

- fact: Two coordinators holding a copy of the assignment risks split-brain
- fact: There is no mechanism to colocate partitions of the group and transaction logs
- fact: If the group coordinator blocks offset fetch while transactions are pending, the txn coordinator does not need to store the assignment
- evidence: <https://kafka-dev.slack.com/archives/KIP447/p1561485061000007>
  > I feel it is a bit awkward to let the TxnCoordinator keeping partition assignments since it is sort of taking over the job of the ConsumerCoordinator, and may likely cause a split-brain problem as two coordinators keep a copy of this assignment which may be different.
- evidence: <https://kafka-dev.slack.com/archives/KIP447/p1561485889000008>
  > The good rationale is that we have no mechanism to colocate partitions
- evidence: <https://kafka-dev.slack.com/archives/KIP447/p1561571987000014>
  > I agree that if we rely on the group coordinator to block on returning offset-fetch-response if read-committed is enabled, then we do not need to store partition assignment on txn coordinator and therefore it's better to still decouple them.
- note: Design decision spread over three messages by two people.

## Q020 · tier B · KIP-447 · test

**Why does the producer take the consumer's group metadata in sendOffsetsToTransaction rather than being given a reference to the consumer itself in initTransactions?**

- fact: Handing the producer a consumer reference is a backdoor that is awkward given package restrictions
- fact: The integration point between producer and consumer should be minimal
- fact: Keeping a consumer reference in the producer raises lifecycle problems such as the consumer being closed
- evidence: <https://kafka-dev.slack.com/archives/KIP447/p1563236856000018>
  > I think the idea is to basically put in a backdoor to give the producer access to the group generationId. It's not clear to me how this would work given package restrictions.
- evidence: <https://kafka-dev.slack.com/archives/KIP447/p1565194792000030>
  > Either way, you need a reference to the consumer. I was mostly just thinking it would be better to reduce the integration point to its minimum.
- evidence: <https://kafka-dev.slack.com/archives/KIP447/p1565053532000027>
  > passing in an entire consumer instance is indeed cumbersome
- note: Two reviewers' objections plus the author's agreement.

## Q021 · tier A · KIP-447 · test

**Why was the default for the broker's expired-transaction cleanup interval lowered from one minute to ten seconds?**

- fact: Expired transactions need to be aborted more frequently
- fact: This reduces the time a consumer waits on a pending offset fetch
- evidence: <https://kafka-dev.slack.com/archives/KIP447/p1581449814000053>
  > The goal here is to trigger the expired transaction more frequently in order to reduce the consumer pending offset fetch wait time.
- note: Reason stated in a single message.

## Q022 · tier T · KIP-447 · test

**Was the Jira issue about moving Kafka Streams to one exactly-once producer per thread filed because a reviewer asked for explanations of the rejected alternatives?**

- fact: Not established: neither artifact references the other
- evidence: <https://issues.apache.org/jira/browse/KAFKA-8587>
  > the root cause is that EOS producer doesn't understand the topic partition move throughout consumer group rebalance.
- evidence: <https://kafka-dev.slack.com/archives/KIP447/p1561261182000001>
  > It would be helpful to have an explanation of why they were rejected.
- note: Jira created 2019-06-23 03:30Z, Ismael's reply 03:39Z. Checked: Ismael's message has no KAFKA key or link to the issue, and the Jira text has no reference to the thread or to Ismael.

## Q023 · tier A · KIP-500 · test

**Why must brokers fetch metadata from the active controller instead of from any of the follower controllers in the metadata quorum?**

- fact: A Raft follower may not have the latest update because it may not have been in the majority that wrote it
- fact: The controller needs to see when brokers stop fetching metadata so it can move them to the fenced state
- evidence: <https://kafka-dev.slack.com/archives/KIP500/p1565029766000014>
  > We also want the controller to know when brokers stop fetching metadata, so that they can be transitioned to a fenced state. This requires fetching from the controller.
- note: Single reply from Colin gives both reasons.

## Q024 · tier B · KIP-500 · test

**Why does the plan not let post-bridge Kafka releases keep running on ZooKeeper, or support pluggable metadata storage, instead of making the metadata quorum the only path?**

- fact: Supporting two metadata code paths means much more work and much more testing
- fact: Doubling the number of configurations to test is a non-starter
- fact: Pluggable storage would limit Kafka to least-common-denominator features and lose metadata-as-an-event-stream
- evidence: <https://kafka-dev.slack.com/archives/KIP500/p1567530287000036>
  > Having to support totally different code paths involves a lot more work and a lot more testing.
- evidence: <https://kafka-dev.slack.com/archives/KIP500/p1567530287000036>
  > Doing this would force us to use only the least-common denominator features of every metadata storage.
- evidence: <https://kafka-dev.slack.com/archives/KIP500/p1567543850000037>
  > especially the part about the onerous testing requirements associated with supporting both Zookeeper and the new metadata quorum simultaneously.
- note: Colin's reply plus the questioner's acceptance in a different message confirm the testing-burden reason. Quotes 1 and 2 come from the same artifact; the third from a second.

## Q025 · tier B · KIP-500 · test

**Why was broker registration moved into its own RPC rather than letting the metadata fetch request double as registration and carry the broker configuration?**

- fact: Putting broker configuration in every metadata fetch would send it over the wire all the time
- fact: A separate registration API avoids overloading the metadata fetch API
- fact: Registration gives the broker a new broker epoch that distinguishes successive incarnations
- evidence: <https://kafka-dev.slack.com/archives/KIP500/p1564791420000008>
  > maybe we should just have a special registration RPC that contains that information, to avoid sending it over the wire all the time.
- evidence: <https://kafka-dev.slack.com/archives/KIP500/p1566244341000018>
  > it might be nice to have a separate broker-registration API to avoid overloading the metadata fetch API.
- evidence: <https://kafka-dev.slack.com/archives/KIP500/p1566255100000019>
  > I removed the sentence about MetadataFetch also serving as the broker registration API.
- note: Colin's first thought, David's suggestion, and Colin's agreement are in three separate messages.

## Q026 · tier A · KIP-500 · dev

**Why does the metadata quorum implement its own Raft replication inside Kafka instead of using an existing library such as Apache Ratis?**

- fact: Kafka's core function is managing logs, so it should not depend on an external system to manage its own logs
- fact: Kafka already stores its own metadata such as consumer offsets and transactions in Kafka topics
- fact: A slightly different replication protocol is needed to avoid the dependency on the controller
- evidence: <https://kafka-dev.slack.com/archives/KIP500/p1566423770000028>
  > We should avoid adding a dependency on an external system to manage the logs of Kafka itself, since that is one of Kafka's core functions.
- note: Direct answer to a reviewer question in one message.

## Q027 · tier T · KIP-500 · test

**Was the removal of the initial-principal request header fields made because a broker-side admin API had to be forwarded to the active controller?**

- fact: Not established: the revert commit and the DecommissionBroker forwarding issue do not reference each other
- evidence: <https://github.com/apache/kafka/commit/9f26906fcc2fd095b7d27c504e342b9a8d619b4b>
  > as we decide to use Envelope for redirection instead of initial principal.
- evidence: <https://kafka-dev.slack.com/archives/KIP500/p1612304940000062>
  > We need to fix this to forward the request to the active controller.
- note: Checked by grep: commit/PR mention KAFKA-9705, #9144, #9523; the Jira mail mentions KAFKA-12275 only. Neither names the other, no shared key. Both concern request forwarding to the controller, about 3 months apart.

## Q028 · tier N · KIP-500 · test

**Why does the controller write metadata snapshots on a periodic schedule rather than after a fixed number of log entries?**

- note: Corpus only says snapshots shorten load time, not durability; no artifact explains the choice of time-based over size-based triggering. Grepped snapshot/periodic.

## Q029 · tier B · KIP-595 · test

**Why does quorum.voters require an explicit numeric ID for every voter instead of just listing host names?**

- fact: IDs let a voter validate incoming vote requests
- fact: Without IDs a voter would have to accept a vote request from any ID
- fact: Hosts can have multiple DNS addresses so a hostname list cannot identify a node
- fact: Without IDs voters could disagree on the proper voter set
- evidence: <https://kafka-dev.slack.com/archives/KIP595/p1596513340000038>
  > It is what enables validation of voter requests. Without it, a voter would have to accept a vote request from any ID.
- evidence: <https://kafka-dev.slack.com/archives/KIP595/p1596577544000039>
  > The fact that nodes can have multiple DNS addresses does make this difficult to do with just a list of hostnames.
- note: Colin objects to hard-coded IDs; Jason's reply gives the reason and Colin's reply confirms the DNS aspect.

## Q030 · tier B · KIP-595 · dev

**Why is the epoch used for leader election limited to 31 bits instead of being widened to 63 bits?**

- fact: The leader epoch is 4 bytes in the existing message format
- fact: Widening it now is difficult
- fact: A batch-attribute hack reusing the producerId as an 8-byte epoch was considered as a workaround
- fact: Colin accepted the hack for now
- evidence: <https://kafka-dev.slack.com/archives/KIP595/p1596513340000038>
  > This is a bit difficult to do at the moment since the leader epoch is 4 bytes in the message format.
- evidence: <https://kafka-dev.slack.com/archives/KIP595/p1596577544000039>
  > I think a hack like the one you suggested would be OK for now.
- note: Colin raises the rollover concern in the vote thread; Jason gives the technical limit; Colin's reply confirms the compromise.

## Q031 · tier A · KIP-595 · dev

**Why do the quorum timeout configs (fetch timeout, election timeout) ship without default values?**

- fact: Right defaults need benchmarking experiments
- fact: Fetch timeout should be on the scale of the ZooKeeper session timeout
- fact: Election timeout should be smaller than the fetch timeout
- evidence: <https://kafka-dev.slack.com/archives/KIP595/p1588218981000006>
  > the reason we did not set any default values for the timeout configurations is that we think it may take some benchmarking experiments to get these defaults right.
- note: Single reply states the rationale.

## Q032 · tier A · KIP-595 · dev

**Why was dynamic quorum reassignment taken out of the Raft metadata quorum proposal and moved to its own proposal?**

- fact: It ties into cluster bootstrapping in a complicated way
- fact: More time was needed for validation
- fact: The core remaining proposal is quorum-based replication
- evidence: <https://kafka-dev.slack.com/archives/KIP595/p1594658583000019>
  > The way this ties into cluster bootstrapping is complicated, so we felt we needed a bit more time for validation.
- note: Single message states the decision and reason.

## Q033 · tier T · KIP-595 · test

**Was the Fetch protocol change for the Raft quorum split into its own change because the design moved to reusing the existing Fetch API instead of a dedicated fetch RPC?**

- fact: Not established: the Jira issue and the mailing-list update do not reference each other
- evidence: <https://kafka-dev.slack.com/archives/KIP595/p1598397540000045>
  > Since this affects inter-broker communication, it is useful to separate this into a separate change.
- evidence: <https://kafka-dev.slack.com/archives/KIP595/p1591768916000014>
  > We will piggy-back on the current Kafka Fetch API instead of inventing a new FetchQuorumRecords RPC.
- note: Both concern Fetch changes for this KIP, about two months apart. Grepped: the Jira-created message (KAFKA-10435) does not mention piggy-backing or the mail thread; the mail update does not mention KAFKA-10435 or a split. The Jira's stated reason is inter-broker compatibility, not the design change.

## Q034 · tier B · KIP-630 · test

**Why does the metadata log use state snapshots to bound its size instead of Kafka's existing key-based log compaction?**

- fact: Compaction is a poor semantic fit because metadata is modelled as a stream of events, not key/value updates
- fact: Compaction's tombstone handling can leave a replica with inconsistent state
- fact: Snapshots allow incremental changes instead of full post images
- fact: Compaction is a poor performance tradeoff when the state is already in memory
- evidence: <https://kafka-dev.slack.com/archives/KIP630/p1596488244000005>
  > First we are arguing that compaction is a poor semantic fit for how we want to model the metadata in the cluster.
- evidence: <https://kafka-dev.slack.com/archives/KIP630/p1596488244000005>
  > compaction gives a poor performance tradeoff when the state is already in memory.
- evidence: <https://kafka-dev.slack.com/archives/KIP630/p1596661122000008>
  > one benefit of snapshotting is that it allows changes to be encoded incrementally instead of using the full post image.
- note: Reason spread over Jason's three-motivation mail and Jun's incremental-encoding mail.

## Q035 · tier B · KIP-630 · test

**Why does a Raft snapshot carry an epoch in its identifier, instead of being identified by end offset alone, given snapshots are only taken below the high watermark?**

- fact: Snapshot offset alone would be unique if data loss is excluded
- fact: The epoch lets the system reason about snapshot state in the presence of data loss
- fact: The snapshot epoch is used as the last fetched epoch in Fetch requests when the follower has a snapshot and an empty log
- evidence: <https://kafka-dev.slack.com/archives/KIP630/p1600980534000014>
  > I think it is important to include the snapshot epoch so that we /can/ reason about the snapshot state in the presence of data loss.
- evidence: <https://kafka-dev.slack.com/archives/KIP630/p1600461490000011>
  > It would help if the document motivated the need to track the snapshot epoch.
- note: Question raised in one mail; reason stated in the reply.

## Q036 · tier B · KIP-630 · test

**Why can a replica keep more than one snapshot on disk even though only the latest snapshot is served to followers?**

- fact: Multiple snapshots avoid invalidating concurrent FetchSnapshot requests for a snapshot about to be deleted
- fact: Generating a snapshot is not atomic with increasing the log begin offset
- fact: Generally only one snapshot is expected on disk
- evidence: <https://kafka-dev.slack.com/archives/KIP630/p1596825205000009>
  > The implementation will still allow for multiple snapshots because generating a snapshot is not atomic with respect to increasing the LBO.
- evidence: <https://kafka-dev.slack.com/archives/KIP630/p1600978757000013>
  > Generally the number of snapshots on disk will be one.
- note: Rationale in Jose's reply to Jun plus later clarification to Jason.

## Q037 · tier A · KIP-630 · test

**Why is the metadata snapshot trigger a minimum count of new records rather than a dirty ratio like topic compaction uses?**

- fact: Calculating a dirty ratio may not be straightforward
- fact: Replicated log records do not map 1:1 to snapshot records
- fact: A heuristic ratio could still be implemented
- evidence: <https://kafka-dev.slack.com/archives/KIP630/p1601347050000019>
  > since calculating a dirty ratio may not be straightforward when replicated log records don't map 1:1 to snapshot records.
- note: Single-message reason.

## Q038 · tier T · KIP-630 · dev

**Was the definition of the fetch-snapshot request and response messages made because of the discussion about keeping more than one snapshot on disk for concurrent snapshot fetches?**

- fact: Not established: the sub-task and the mail do not reference each other
- evidence: <https://kafka-dev.slack.com/archives/KIP630/p1597253640000010>
  > KIP-630: messafe for fetch snapshot and fetch
- evidence: <https://kafka-dev.slack.com/archives/KIP630/p1596825205000009>
  > The KIP proposes keeping more than one snapshot to not invalidate any pending/concurrent `FetchSnapshot` that are attempting to fetch a snapshot that can be deleted.
- note: Jira sub-task (2020-08-12) is 5 days after the mail (2020-08-07); grep shows the mail does not mention KAFKA-10393 and the Jira text has no link to the mail; only shared token is the KIP number.

## Q039 · tier A · KIP-679 · test

**Why does kafka-console-producer default request-required-acks to -1 instead of keeping the old default of 1?**

- fact: The producer default for enable.idempotence became true
- fact: Idempotence requires acks=all, so the console producer default had to be set to -1 to match
- evidence: <https://kafka-dev.slack.com/archives/KIP679/p1643943115000011>
  > But after this KIP, we set the default enable.idempotence to true, so we have to also set the default acks config here to -1 for this change.
- note: Reason stated in a single mail message.

## Q040 · tier A · KIP-679 · test

**Why was it considered acceptable to change the producer acks default from 1 to all?**

- fact: A performance analysis of acks and max.in.flight.requests.per.connection was done
- fact: Changing acks to all does not significantly increase latency or reduce throughput
- evidence: <https://issues.apache.org/jira/browse/KAFKA-10619>
  > indicates that changing `acks` from `1` to `all` won't increase the latency and decrease the throughput in a significant way.
- note: Single Jira issue states the rationale.

## Q041 · tier B · KIP-679 · dev

**Why did producers in 3.0 and 3.1 stay non-idempotent by default even though enable.idempotence defaults to true?**

- fact: The config validator and the idempotenceEnabled check were not adjusted when the default changed
- fact: Idempotence was only on if explicitly set by the user
- fact: Fixed by correcting ProducerConfig#idempotenceEnabled and moving validation into ProducerConfig
- evidence: <https://issues.apache.org/jira/browse/KAFKA-13598>
  > In KAFKA-10619, we intended to enable idempotence by default, but this was not achieved due to a bug in the config validation logic.
- evidence: <https://github.com/apache/kafka/commit/e6db0ca48c42c03655e3781b46ac09dae75cf33e>
  > In v3.0, we changed the default value for `enable.idempotence` to true, but we didn't adjust the validator and the `idempotence` enabled check method.
- note: Jira issue plus the fixing commit confirm the cause.

## Q042 · tier B · KIP-679 · test

**Why does the producer silently turn idempotence off when the user sets conflicting acks, retries or max.in.flight values instead of failing config validation?**

- fact: Idempotence is enabled by default, so existing producers with conflicting configs would otherwise break
- fact: Disabling idempotence on conflict mitigates the compatibility impact
- fact: Logged at info for acks/retries and warn for max.in.flight
- evidence: <https://github.com/apache/kafka/commit/7c280c1d5f6267acbbebd10d3e58ea4b8fe7a4ef>
  > This mitigates compatibility impact of enabling idempotence by default.
- evidence: <https://issues.apache.org/jira/browse/KAFKA-13598>
  > we'll disable idempotent producer when acks/retries/max.in.flight config conflicts, to avoid breaking existing producers.
- note: Commit message and the parent Jira issue both give the compatibility rationale.

## Q043 · tier T · KIP-679 · test

**Was the producer change that disables idempotence on conflicting acks/retries/max.in.flight configs made because of the concern that default idempotence can exhaust broker memory with too many producer ids?**

- fact: Not established: neither artifact references the other
- evidence: <https://kafka-dev.slack.com/archives/KIP679/p1619201226000010>
  > This has the ability to crash a broker with OutOfMemory exception whenever there are too many producerIds.
- evidence: <https://github.com/apache/kafka/pull/11788>
  > This mitigates compatibility impact of enabling idempotence by default.
- note: Grep: the OOM mail cites only KAFKA-10619; the PR/commit text never mentions OOM, producer ids, or that mail. Correct answer: not established.

## Q044 · tier A · KIP-848 · test

**Why does the Kafka 4.0 consumer still default to the classic rebalance protocol even though the new protocol is production-ready and enabled by default on the broker?**

- fact: A 4.0 consumer defaulting to the new protocol would not work by default with brokers older than 4.0
- fact: That would be a poor user experience because most deployments will upgrade to 4.0 gradually
- evidence: <https://kafka-dev.slack.com/archives/KIP848/p1734530903000183>
  > The key concern is that the consumer shipped with Apache Kafka 4.0 would not work by default with brokers older than 4.0, which we believe would result in a poor user experience.
- note: Reason stated directly in the single 4.0 update mail.

## Q045 · tier A · KIP-848 · test

**Why doesn't the consumer automatically fall back from the new rebalance protocol to the classic one when the broker doesn't support it, and instead require users to opt in explicitly?**

- fact: The two protocols differ significantly (static membership, assignors, configs, metrics, behavior)
- fact: So automatic fallback was unfeasible and users must explicitly choose when to migrate
- evidence: <https://kafka-dev.slack.com/archives/KIP848/p1734530903000183>
  > However, the significant differences between the two protocols made this unfeasible.
- evidence: <https://kafka-dev.slack.com/archives/KIP848/p1734530903000183>
  > Given these differences, we believe users must explicitly choose when to migrate from the old protocol to the new protocol as already planned in the KIP.
- note: Single-artifact reason with a concrete list of differences.

## Q046 · tier B · KIP-848 · test

**Why was the switch to the new group coordinator tied to a major release (4.x) rather than shipped in a minor release behind a flag?**

- fact: The group coordinator is being rewritten in Java so internals such as the threading model change, so the switch from old to new coordinator was tied to a major release instead of a flag
- fact: Enabling the feature on clients needs two rolling bounces (swap in the code, then set the flag), which also fits a major version
- evidence: <https://kafka-dev.slack.com/archives/KIP848/p1657628552000006>
  > Therefore, I wanted to tighten the switch from the old group coordinator to the new group coordinator to a major release.
- evidence: <https://kafka-dev.slack.com/archives/KIP848/p1657569157000004>
  > At that time, to enable the feature the clients need to first swap-in the bytecode with a rolling bounce and then set the flag with a second rolling bounce, and hence we feel it's better to be released in a major version.
- note: Two authors give complementary reasons in different messages of the discussion.

## Q047 · tier B · KIP-848 · test

**Why were topic IDs for the OffsetFetch/OffsetCommit APIs split out and deferred to a later release instead of being delivered together with the rest of the new consumer group protocol?**

- fact: Introducing the new API versions is easier once the old group coordinator is gone
- fact: The old group coordinator was planned to be deleted in a later release (4.2 planned)
- evidence: <https://issues.apache.org/jira/browse/KAFKA-18328?focusedCommentId=17907172>
  > It will be easier to introduce the new API versions when the old group coordinator is gone.
- evidence: <https://kafka-dev.slack.com/archives/KIP848/p1742569740000190>
  > In 4.2.0, we should be able to delete the old group coordinator.
- note: Jira comment gives the reason; a second Jira issue confirms the dependency (old coordinator removal).

## Q048 · tier T · KIP-848 · test

**Was making the new group coordinator the default in trunk done because the Streams system tests for the new group protocol config were closed as won't fix?**

- fact: Not established: neither artifact references the other
- evidence: <https://github.com/apache/kafka/pull/16945>
  > This patch makes the new group coordinator, introduced as part of KIP-848, the default.
- evidence: <https://kafka-dev.slack.com/archives/KIP848/p1724271000000171>
  > They've stated that this is not the approach they'll take, so closing as won't fix.
- note: PR and Jira-resolution mail are from the same day (2024-08-21). Checked: the PR text does not mention KAFKA-16443/16442/16441 and the Jira mails do not mention PR 16945 or the default switch; no shared key or URL.

## Q049 · tier N · KIP-848 · test

**Why does the broker cap the number of members in a consumer group with a configurable maximum size instead of leaving group size unbounded?**

- fact: No corpus artifact states the reason
- note: Grepped the corpus and answer key for max.size, maximum number of members and group size: no hits.

## Q050 · tier B · KIP-890 · dev

**Why does the broker retry AddPartitionsToTxn on its own when it hits CONCURRENT_TRANSACTIONS, with separate backoff settings, instead of just returning the error to the producer to retry?**

- fact: CONCURRENT_TRANSACTIONS is common after a commit while markers are still propagating
- fact: Client-side retry of the produce request is frequent and expensive
- fact: Routing the call through produce reverted to the slower default client retry backoff
- fact: Server-side backoff defaults are kept short to avoid client timeouts yet long enough for markers to propagate
- evidence: <https://kafka-dev.slack.com/archives/KIP890/p1739227441000106>
  > This error is common after the transaction is committed but before the markers are fully propagated to all the involved partitions. With the server side retry, the client can avoid the frequent and expensive retry for the produce request.
- evidence: <https://issues.apache.org/jira/browse/KAFKA-18654>
  > With KIP-890 and making the call through the produce path, we go back to the default retry backoff which takes longer.
- evidence: <https://kafka-dev.slack.com/archives/KIP890/p1739316392000108>
  > We want this value to be small to avoid client side timeout and retry, but also long enough for the markers to propagate.
- note: Mail announces server-side retry and why; Jira explains the regression that motivated it; reply explains defaults.

## Q051 · tier B · KIP-890 · dev

**Why did the transaction protocol add a dedicated abortable-transaction error that the server can return on any failure, and bump all the transactional APIs for it, instead of reusing UNKNOWN_PRODUCER_ID?**

- fact: UNKNOWN_PRODUCER_ID has a long, complicated handling history
- fact: A new error lets the server tell new clients to simply abort the transaction
- fact: All transactional APIs are bumped to future-proof the error
- fact: Good generic error codes that older clients supported could not be found
- evidence: <https://kafka-dev.slack.com/archives/KIP890/p1670372533000009>
  > the UNKNOWN_PRODUCER_ID error has a pretty long and complicated history. Because of this, I propose adding a new error code ABORTABLE_ERROR that when encountered by new clients (gated by the produce request version) will simply abort the transaction.
- evidence: <https://kafka-dev.slack.com/archives/KIP890/p1710812397000098>
  > We ran into issues finding good/generic error codes that older clients could support while working on this KIP, so this should help in the future.
- note: Two messages from the author, months apart: initial proposal rationale and later reason for bumping all 6 APIs.

## Q052 · tier B · KIP-890 · test

**Why were the transactional state-record and protocol changes gated behind a new transaction version feature instead of the metadata version / inter-broker protocol version?**

- fact: A separate feature for transactions is used to version-gate flexible state records and the new protocol
- fact: The direction is to move away from MV gating inter-broker protocols
- fact: MV should ideally be used only for metadata changes
- evidence: <https://kafka-dev.slack.com/archives/KIP890/p1706657503000089>
  > I think it makes the most sense to create a separate feature for transactions and use that to version gate the features we need to version gate
- evidence: <https://kafka-dev.slack.com/archives/KIP890/p1707237585000097>
  > I think the idea is to move away from MV gating inter broker protocols. Ideally we can get to a state where MV is just used for metadata changes.
- note: Decision in one message, rationale in the follow-up reply.

## Q053 · tier A · KIP-890 · test

**Why does the new client treat INVALID_PID_MAPPING as fatal to the producer rather than recovering by re-initialising the producer ID?**

- fact: Recovering after the transactional id expires can duplicate processing and violate EOS
- fact: Epoch bump per transaction means InitProducerId is no longer used to recover
- fact: Fatal matches the application-recoverable category in KIP-1050
- evidence: <https://kafka-dev.slack.com/archives/KIP890/p1731621096000105>
  > if we recover from invalid pid mapping, we can duplicate this processing
- evidence: <https://kafka-dev.slack.com/archives/KIP890/p1731621096000105>
  > Thus, INVALID_PID_MAPPING should be fatal to the producer and as part of KIP-890 the new client in 4.0 will treat the exception as fatal.
- note: Whole reason with worked example is in one message.

## Q054 · tier T · KIP-890 · test

**Was the AddPartitionsToTxn verifyOnly and batching protocol change made because users wanted a way to turn off partition verification to meet latency goals?**

- fact: Not established: neither artifact references the other
- evidence: <https://kafka-dev.slack.com/archives/KIP890/p1679097178000064>
  > This will be for performance-conscious customers who can sacrifice possible hanging transactions in order achieve latency goals.
- evidence: <https://github.com/apache/kafka/commit/29a1a16668d76a1cc04ec9e39ea13026f2dce1de>
  > Clients should only be able to send up to version 3 requests and that is enforced by using a client builder.
- note: Commit 2023-03-07 and config-disable mail 2023-03-17 are adjacent in time and topic. Grepped: the commit text has no mention of the config or mail; the mail has no PR number, Jira key or URL of the commit. Commit predates the mail, so causation is not supported.

## Q055 · tier N · KIP-890 · test

**Why does the verification feature expose only a verification-time metric and a failure-rate metric rather than per-topic or per-partition metrics?**

- fact: Not stated in any artifact
- note: Metric names appear only in the KIP page; grep of corpus finds no mention of VerificationTimeMs/VerificationFailureRate or any rationale.
