-- SQL Server Agent jobs (msdb). Nightly at 01:00 and monthly regulator export.
USE msdb;
GO
EXEC dbo.sp_add_job @job_name = N'ClaimsHub - Nightly reserve recalculation';
EXEC dbo.sp_add_jobstep @job_name = N'ClaimsHub - Nightly reserve recalculation', @step_name = N'Recalculate',
     @subsystem = N'TSQL', @database_name = N'Claims', @command = N'EXEC claims.usp_RecalculateReserves;';
EXEC dbo.sp_add_schedule @schedule_name = N'Nightly 01:00', @freq_type = 4, @freq_interval = 1, @active_start_time = 010000;
EXEC dbo.sp_attach_schedule @job_name = N'ClaimsHub - Nightly reserve recalculation', @schedule_name = N'Nightly 01:00';
EXEC dbo.sp_add_jobserver @job_name = N'ClaimsHub - Nightly reserve recalculation';

EXEC dbo.sp_add_job @job_name = N'ClaimsHub - Close stale claims';
EXEC dbo.sp_add_jobstep @job_name = N'ClaimsHub - Close stale claims', @step_name = N'Close',
     @subsystem = N'TSQL', @database_name = N'Claims', @command = N'EXEC claims.usp_CloseStaleClaims @IdleDays = 365;';
EXEC dbo.sp_attach_schedule @job_name = N'ClaimsHub - Close stale claims', @schedule_name = N'Nightly 01:00';
EXEC dbo.sp_add_jobserver @job_name = N'ClaimsHub - Close stale claims';
GO
