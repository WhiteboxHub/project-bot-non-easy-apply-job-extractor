"""
Metrics collection and reporting for job extraction runs.
Tracks attempts, successes, failures, and provides end-of-run summaries.
"""

import time
from typing import Dict, List
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RunMetrics:
    """Metrics for a single extraction run"""
    
    # Run metadata
    run_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    
    # Candidate info
    candidate_id: str = "unknown"
    keywords: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    
    # Extraction metrics
    jobs_found: int = 0
    jobs_saved: int = 0
    jobs_skipped_duplicate: int = 0
    jobs_skipped_easy_apply: int = 0
    jobs_failed: int = 0
    
    # Navigation metrics
    pages_visited: int = 0
    scroll_attempts: int = 0
    
    # Error tracking
    errors: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[Dict[str, str]] = field(default_factory=list)
    
    # Per-step retry counts
    retry_counts: Dict[str, int] = field(default_factory=dict)
    
    def record_job_found(self):
        """Record a job was found"""
        self.jobs_found += 1
    
    def record_job_saved(self):
        """Record a job was successfully saved"""
        self.jobs_saved += 1
    
    def record_job_skipped_duplicate(self):
        """Record a job was skipped as duplicate"""
        self.jobs_skipped_duplicate += 1
    
    def record_job_skipped_easy_apply(self):
        """Record a job was skipped as Easy Apply"""
        self.jobs_skipped_easy_apply += 1
    
    def record_job_failed(self):
        """Record a job save failed"""
        self.jobs_failed += 1
    
    def record_page_visited(self):
        """Record a page was visited"""
        self.pages_visited += 1
    
    def record_scroll_attempt(self):
        """Record a scroll attempt"""
        self.scroll_attempts += 1
    
    def record_error(self, step: str, message: str, exception_type: str = ""):
        """Record an error"""
        self.errors.append({
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "message": message,
            "exception_type": exception_type
        })
    
    def record_warning(self, step: str, message: str):
        """Record a warning"""
        self.warnings.append({
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "message": message
        })
    
    def record_retry(self, step: str):
        """Record a retry attempt for a step"""
        if step not in self.retry_counts:
            self.retry_counts[step] = 0
        self.retry_counts[step] += 1
    
    def finalize(self):
        """Mark the run as complete"""
        self.end_time = time.time()
    
    def get_duration(self) -> float:
        """Get run duration in seconds"""
        end = self.end_time if self.end_time > 0 else time.time()
        return end - self.start_time
    
    def get_summary(self) -> str:
        """Generate a formatted summary report"""
        duration_mins = self.get_duration() / 60
        
        summary = f"""
{'=' * 70}
📊 EXTRACTION RUN SUMMARY
{'=' * 70}

Run ID: {self.run_id}
Candidate: {self.candidate_id}
Duration: {duration_mins:.2f} minutes
Started: {datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S')}
Ended: {datetime.fromtimestamp(self.end_time).strftime('%Y-%m-%d %H:%M:%S') if self.end_time > 0 else 'In Progress'}

{'─' * 70}
SEARCH PARAMETERS
{'─' * 70}
Keywords: {', '.join(self.keywords) if self.keywords else 'None'}
Locations: {', '.join(self.locations) if self.locations else 'None'}

{'─' * 70}
JOB EXTRACTION RESULTS
{'─' * 70}
✅ Jobs Saved:              {self.jobs_saved:>6}
🔍 Jobs Found (Total):      {self.jobs_found:>6}
⏭️  Skipped (Duplicate):    {self.jobs_skipped_duplicate:>6}
⏭️  Skipped (Easy Apply):   {self.jobs_skipped_easy_apply:>6}
❌ Failed to Save:          {self.jobs_failed:>6}

{'─' * 70}
NAVIGATION METRICS
{'─' * 70}
Pages Visited:              {self.pages_visited:>6}
Scroll Attempts:            {self.scroll_attempts:>6}

{'─' * 70}
ERROR & RETRY SUMMARY
{'─' * 70}
Total Errors:               {len(self.errors):>6}
Total Warnings:             {len(self.warnings):>6}
"""
        
        if self.retry_counts:
            summary += "\nRetries by Step:\n"
            for step, count in sorted(self.retry_counts.items(), key=lambda x: x[1], reverse=True):
                summary += f"  {step:<30} {count:>6}\n"
        
        if self.errors:
            summary += f"\n{'─' * 70}\n"
            summary += "RECENT ERRORS (Last 5):\n"
            summary += f"{'─' * 70}\n"
            for error in self.errors[-5:]:
                summary += f"  [{error['step']}] {error['message'][:80]}\n"
        
        summary += f"\n{'=' * 70}\n"
        
        return summary


class MetricsCollector:
    """
    Global metrics collector for tracking multiple runs.
    Singleton pattern to ensure single instance across the application.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.current_run = None
            cls._instance.all_runs = []
        return cls._instance
    
    def start_run(self, candidate_id: str, keywords: List[str], locations: List[str]) -> RunMetrics:
        """Start a new run and return the metrics object"""
        self.current_run = RunMetrics(
            candidate_id=candidate_id,
            keywords=keywords,
            locations=locations
        )
        return self.current_run
    
    def end_run(self):
        """Finalize the current run and archive it"""
        if self.current_run:
            self.current_run.finalize()
            self.all_runs.append(self.current_run)
            print(self.current_run.get_summary())
            self.current_run = None
    
    def get_current_run(self) -> RunMetrics:
        """Get the current run metrics"""
        return self.current_run
    
    def get_all_runs(self) -> List[RunMetrics]:
        """Get all completed runs"""
        return self.all_runs


# Global singleton instance
metrics = MetricsCollector()
