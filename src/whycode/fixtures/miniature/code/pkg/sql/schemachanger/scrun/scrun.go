// Copyright 2021 The Cockroach Authors.
//
// Use of this software is governed by the CockroachDB Software License
// included in the /LICENSE file.

// Miniature of pkg/sql/schemachanger/scrun/scrun.go for the fixture history.

package scrun

import (
	"context"

	"github.com/cockroachdb/cockroach/pkg/settings"
	"github.com/cockroachdb/cockroach/pkg/sql/schemachanger/scplan"
)

var enforcePlannerSanityCheck = settings.RegisterBoolSetting(
	settings.ApplicationLevel,
	"sql.schemachanger.strict_planning_sanity_check.enabled",
	"enforce strict sanity checks on the schema changer plan",
	false,
)

// RunStatementPhase executes in-transaction schema changes for the targeted
// state.
func RunStatementPhase(ctx context.Context, sv *settings.Values, state scplan.State) (scplan.State, error) {
	return makeState(ctx, sv, state)
}

// RunPreCommitPhase is part of the transaction commit process.
func RunPreCommitPhase(ctx context.Context, sv *settings.Values, state scplan.State) (scplan.State, error) {
	return makeState(ctx, sv, state)
}

// RunSchemaChangesInJob contains the business logic for the schema change job.
func RunSchemaChangesInJob(ctx context.Context, sv *settings.Values, state scplan.State) error {
	_, err := makeState(ctx, sv, state)
	return err
}

func makeState(ctx context.Context, sv *settings.Values, state scplan.State) (scplan.State, error) {
	plan, err := scplan.MakePlan(ctx, state, scplan.Params{
		EnforcePlannerSanityCheck: enforcePlannerSanityCheck.Get(sv),
	})
	if err != nil {
		return scplan.State{}, err
	}
	return plan.CurrentState, nil
}
