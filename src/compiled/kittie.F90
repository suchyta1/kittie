module adios2_coupling_base
	use mpi
	use adios2

	implicit none

	character(len=8), parameter :: writing=".writing"
	character(len=8), parameter :: reading=".reading"
	integer :: iounit=20


	type coupling_helper
		character(len=:), allocatable :: filename
		type(adios2_engine) :: engine
		type(adios2_io) :: io
		integer :: mode
		integer :: comm
		logical :: usesfile
		logical :: instep=.false.
		logical :: alive=.false.
		character(len=:), allocatable :: engine_type
	end type coupling_helper


	contains

		function string_copy(thing) result(new)
			character(len=*), intent(in) :: thing
			character(len=:), allocatable :: new
			allocate(character(len_trim(thing)) :: new)
			new = thing
		end function string_copy


		function capitalize(strIn) result(strOut)
			character(len=*), intent(in) :: strIn
			character(len=:), allocatable :: strOut
			integer :: i,j

			strOut = string_copy(strIn)
			do i = 1, len(strOut)
				j = iachar(strIn(i:i))
				if (j>= iachar("a") .and. j<=iachar("z") ) then
					strOut(i:i) = achar(iachar(strIn(i:i))-32)
				else
					strOut(i:i) = strIn(i:i)
				end if
			end do
		end function capitalize


		subroutine delete_existing(fname)
			character(len=*), intent(in) :: fname
			integer :: stat
			open(unit=iounit, iostat=stat, file=fname, status='old')
			close(iounit, status="delete")
		end subroutine delete_existing


		subroutine touch_file(fname)
			character(len=*), intent(in) :: fname
			open(unit=iounit, file=fname, status='new')
			close(iounit)
		end subroutine touch_file


		subroutine until_nonexistent(helper)
			type(coupling_helper), intent(in) :: helper
			logical :: rexists, wexists

			do while (.true.)

				if (helper%mode == adios2_mode_read) then
					inquire(file=trim(helper%filename), exist=rexists)
					if (.not.rexists) then
						cycle
					end if
				end if

				inquire(file=trim(helper%filename)//reading, exist=rexists)
				inquire(file=trim(helper%filename)//writing, exist=wexists)

				if (rexists .and. wexists) then
					if  (helper%mode == adios2_mode_read) then
						call delete_existing(helper%filename//reading)
					end if
					cycle
				else if (rexists .or. wexists) then
					cycle
				else
					exit
				end if

			end do

			if (helper%mode == adios2_mode_write) then
				call touch_file(trim(helper%filename)//writing)
			else if (helper%mode == adios2_mode_read) then
				call touch_file(trim(helper%filename)//reading)
			end if

		end subroutine until_nonexistent


		subroutine lock_logic(helper, yes)
			type(coupling_helper), intent(in) :: helper
			logical, intent(in) :: yes

			if (yes) then
				call until_nonexistent(helper)
			else
				if (helper%mode == adios2_mode_write) then
					call delete_existing(helper%filename//writing)
				else if (helper%mode == adios2_mode_read) then
					call delete_existing(helper%filename//reading)
				end if
			end if

		end subroutine lock_logic


		subroutine lock_state(helper, yes)
			type(coupling_helper), intent(in) :: helper
			logical, intent(in) :: yes

			integer :: ierr, rank, stat

			if (.not. yes) then
				call mpi_barrier(helper%comm, ierr)
			end if

			call mpi_comm_rank(helper%comm, rank, ierr)
			if (rank == 0) then
				call lock_logic(helper, yes)
			end if

			if (yes) then
				call mpi_barrier(helper%comm, ierr)
			end if

		end subroutine lock_state


		subroutine adios2_couple_end_step(helper, ierr)
			type(coupling_helper), intent(inout) :: helper
			integer, intent(out) :: ierr

			if (helper%usesfile) then
				call lock_state(helper, .true.)
			end if

			call adios2_end_step(helper%engine, ierr)
			helper%instep = .false.

			if (helper%usesfile) then
				call lock_state(helper, .false.)
				if (helper%mode == adios2_mode_read) then
					call adios2_close(helper%engine, ierr)
					call adios2_remove_all_variables(helper%io, ierr)
				end if
			end if

		end subroutine adios2_couple_end_step


		function which_engine(io) result(res)
			type(adios2_io), intent(in) :: io
			integer :: ierr
			character(:), allocatable :: res
			!character(:), allocatable :: engine_type

			!call adios2_io_engine_type(io, engine_type, ierr)
			!res = capitalize(engine_type)
			!deallocate(engine_type)

			res = capitalize(io%engine_type)

		end function which_engine


		function uses_files(engine_type) result(res)
			character(len=*), intent(in) :: engine_type
			integer :: ierr
			logical :: res

			if ((engine_type == 'BPFILE') .or. (engine_type == 'HDF5')) then
				res = .true.
			else
				res = .false.
			end if
		end function uses_files


		recursive subroutine file_seek(helper, step)
			type(coupling_helper), intent(inout) :: helper
			integer, intent(in) :: step
			integer :: ierr, i
			integer(kind=8) :: current_step
			logical :: found

			found = .false.
			current_step = -1
			call lock_state(helper, .true.)
			call adios2_open(helper%engine, helper%io, helper%filename, helper%mode, helper%comm, ierr)

			do while (.true.)
				call adios2_begin_step(helper%engine, adios2_step_mode_next_available, ierr)

				if (ierr == 0) then
					current_step = current_step + 1
				else
					exit
				end if

				if (current_step == step) then
					found = .true.
					exit
				end if

				call adios2_end_step(helper%engine, ierr)
			end do

			call lock_state(helper, .false.)
			if (.not.found) then
				call adios2_close(helper%engine, ierr)
				call adios2_remove_all_variables(helper%io, ierr)
				call file_seek(helper, step)
			end if

		end subroutine file_seek


		subroutine adios2_couple_open(helper)
			type(coupling_helper), intent(inout) :: helper
			integer :: ierr
			if (helper%usesfile) then
				call lock_state(helper, .true.)
			end if
			call adios2_open(helper%engine, helper%io, helper%filename, helper%mode, helper%comm, ierr)
			if (helper%usesfile) then
				call lock_state(helper, .false.)
			end if
		end subroutine adios2_couple_open


		! Roughly the idea is "push/fetch the step I want, without me having to worry about how I do that in a safe way for different types of I/O".
		! In detail, this is something of a combination of adios2_open() and adios2_begin_step() depending what engine type you're using.
		subroutine adios2_couple_start(helper, fname, io, mode, comm, step, dir, hint)

			! This is intent(inout) for a reason that isn't super important, but someone might want. 
			! I copy back the helper%io that gets set into the argument io
			type(adios2_io), intent(inout) :: io

			type(coupling_helper), intent(inout) :: helper
			character(len=*), intent(in) :: fname
			integer, intent(in) :: mode, comm
			character(len=*), intent(in), optional :: dir, hint
			integer, intent(in), optional :: step

			type(adios2_engine) :: engine
			integer :: ierr

			if (.not.helper%alive) then
				helper%comm = comm
				helper%engine_type = which_engine(io)
				helper%usesfile = uses_files(helper%engine_type)
				helper%mode = mode
				if (present(dir)) then
					helper%filename = string_copy(trim(dir)//"/"//trim(fname))
				else
					helper%filename = string_copy(trim(fname))
				end if
			end if

			if (.not.helper%alive) then
				helper%io = io
			end if


			if (helper%mode == adios2_mode_write) then
				if (.not.helper%alive) then
					call adios2_couple_open(helper)
				end if
				call adios2_begin_step(helper%engine, adios2_step_mode_append, ierr)

			else if (helper%mode == adios2_mode_read) then
				if (helper%usesfile) then
					if (.not.present(step)) then
						write (*, "('If reading from file for coupling, must give what step you want to read from')")
						stop
					end if
					call file_seek(helper, step)
				else
					if (.not.helper%alive) then
						call adios2_couple_open(helper)
					end if
					call adios2_begin_step(helper%engine, adios2_step_mode_next_available, ierr)
				end if

			end if

			helper%alive = .true.
			io = helper%io
		end subroutine adios2_couple_start


end module adios2_coupling_base

