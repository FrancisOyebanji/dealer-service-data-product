"""Streaming ingestion — Apache Beam / Dataflow: Pub/Sub -> BigQuery.

Production Dataflow pipeline (the deployment target for the streaming path in the
reference architecture). Reads service-telemetry events from Pub/Sub, validates
and enriches them, and writes to a partitioned/clustered BigQuery table via the
Storage Write API with exactly-once semantics. Not executed in CI (no Dataflow
runner); the local proof validates the resulting BigQuery model on DuckDB.

Run:  python gcp/beam/streaming_pipeline.py \
        --project <p> --region <r> --runner DataflowRunner \
        --input_subscription projects/<p>/subscriptions/service-events \
        --output_table <p>:dealer_service.fact_repair_orders
"""
from __future__ import annotations

import argparse
import json

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions

VALID_SERVICE_TYPES = {"scheduled_maintenance", "warranty_repair",
                       "customer_pay_repair", "recall", "diagnostic"}


class ParseAndValidate(beam.DoFn):
    """Parse the JSON event; route invalid records to a dead-letter side output."""
    DLQ = "dead_letter"

    def process(self, element):
        try:
            e = json.loads(element.decode("utf-8"))
            assert e.get("ro_number") and e.get("service_date")
            assert e.get("service_type") in VALID_SERVICE_TYPES
            assert float(e.get("total_amount", 0)) >= 0
            yield {
                "ro_number": e["ro_number"], "dealer_key": int(e["dealer_key"]),
                "service_date": e["service_date"], "service_type": e["service_type"],
                "total_amount": float(e["total_amount"]),
                "satisfaction_score": e.get("satisfaction_score"),
            }
        except Exception as ex:                       # noqa: BLE001
            yield beam.pvalue.TaggedOutput(self.DLQ, {"raw": element.decode("utf-8", "replace"),
                                                      "error": str(ex)})


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_subscription", required=True)
    parser.add_argument("--output_table", required=True)
    parser.add_argument("--dlq_table", default=None)
    args, beam_args = parser.parse_known_args(argv)

    opts = PipelineOptions(beam_args)
    opts.view_as(StandardOptions).streaming = True

    schema = ("ro_number:STRING,dealer_key:INTEGER,service_date:DATE,"
              "service_type:STRING,total_amount:NUMERIC,satisfaction_score:INTEGER")

    with beam.Pipeline(options=opts) as p:
        parsed = (p
            | "ReadPubSub" >> beam.io.ReadFromPubSub(subscription=args.input_subscription)
            | "ParseValidate" >> beam.ParDo(ParseAndValidate())
                .with_outputs(ParseAndValidate.DLQ, main="valid"))

        (parsed.valid | "WriteBQ" >> beam.io.WriteToBigQuery(
            args.output_table, schema=schema,
            write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
            create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
            method=beam.io.WriteToBigQuery.Method.STORAGE_WRITE_API))  # exactly-once

        if args.dlq_table:
            (parsed[ParseAndValidate.DLQ] | "WriteDLQ" >> beam.io.WriteToBigQuery(
                args.dlq_table, schema="raw:STRING,error:STRING",
                write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND))


if __name__ == "__main__":
    run()
