// Copyright 2015 The Cockroach Authors.
//
// Use of this software is governed by the CockroachDB Software License
// included in the /LICENSE file.

// Miniature of pkg/sql/schema_changer.go for the fixture history. Bodies are
// trimmed; names and the setting registration follow the real file.

package sql

import (
	"context"
	"time"

	"github.com/cockroachdb/cockroach/pkg/settings"
	"github.com/cockroachdb/cockroach/pkg/sql/catalog"
	"github.com/cockroachdb/cockroach/pkg/util/log"
	"github.com/cockroachdb/cockroach/pkg/util/retry"
	"github.com/cockroachdb/errors"
)

// schemaChangeJobMaxRetryBackoff caps the exponential backoff between
// retries of a schema change job.
var schemaChangeJobMaxRetryBackoff = settings.RegisterDurationSetting(
	settings.ApplicationLevel,
	"schemachanger.job.max_retry_backoff",
	"the exponential back-off when retrying jobs for schema changes",
	20*time.Second,
	settings.PositiveDuration,
)

// SchemaChanger is used to change the schema on a table.
type SchemaChanger struct {
	descID   int64
	settings *settings.Values
}

// isPermanentSchemaChangeError returns true if the error results in
// a permanent failure of a schema change.
func isPermanentSchemaChangeError(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, catalog.ErrDescriptorNotFound) {
		return true
	}
	return false
}

// exec executes the entire schema change in steps.
func (sc *SchemaChanger) exec(ctx context.Context) error {
	opts := retry.Options{InitialBackoff: 20 * time.Millisecond, Multiplier: 1.5}
	for r := retry.Start(opts); r.Next(); {
		opts.MaxBackoff = schemaChangeJobMaxRetryBackoff.Get(sc.settings)
		err := sc.step(ctx)
		if err == nil || isPermanentSchemaChangeError(err) {
			return err
		}
		log.Warningf(ctx, "schema change job will retry with backoff: %v", err)
	}
	return nil
}

func (sc *SchemaChanger) step(ctx context.Context) error {
	return sc.runBackfill(ctx)
}

// runBackfill runs the backfill for the schema changer.
func (sc *SchemaChanger) runBackfill(ctx context.Context) error {
	return nil
}

// maybeUpdateZoneConfigsForPKChange moves zone configs for any rewritten
// indexes from the old index over to the new index.
func (sc *SchemaChanger) maybeUpdateZoneConfigsForPKChange(ctx context.Context) error {
	return nil
}
